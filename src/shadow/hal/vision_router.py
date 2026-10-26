"""Privacy-aware routing for SHADOW's interactive vision requests."""

from dataclasses import dataclass
from typing import Any

from .provider_pool import ProviderPool


@dataclass(frozen=True)
class VisionRoutingResult:
    """Result of a vision-routing operation."""

    text: str
    route: str
    provider: str = ""


class VisionRoutingError(RuntimeError):
    """Raised when no configured vision route can complete a request."""


class VisionRouter:
    """Route explicitly triggered image analysis to cloud or local vision.

    Cloud use requires all of the following:
      - cloud vision enabled in configuration;
      - explicit vision-cloud consent;
      - network connectivity;
      - a non-sensitive window;
      - authorization for this particular cloud upload.

    Continuous/background vision should use the local VisionService
    directly and must not be routed through this class.
    """

    def __init__(
        self,
        local_service,
        cloud_pool: ProviderPool | None,
        config: dict,
        health,
        consent_store,
    ):
        self.local_service = local_service
        self.cloud_pool = cloud_pool
        self.config = config
        self.health = health
        self.consent_store = consent_store
        self.last_result: VisionRoutingResult | None = None

    def analyze(
        self,
        image_bytes: bytes,
        task: str = "caption",
        prompt: str = "",
        *,
        authorized: bool = False,
        window_metadata: dict[str, Any] | None = None,
        local_only: bool = False,
    ) -> str:
        """Analyze an image and return its text result.

        The string return type preserves compatibility with VisionService.
        Routing details are available in ``last_result``.
        """
        metadata = window_metadata or {}

        if not isinstance(image_bytes, bytes) or not image_bytes:
            raise VisionRoutingError("The captured image is empty.")

        # Privacy-sensitive windows never reach the cloud.
        if metadata.get("is_sensitive", False):
            return self._analyze_local(image_bytes, task, prompt)

        if local_only:
            return self._analyze_local(image_bytes, task, prompt)

        # DEBUG: Print the eligibility check result
        eligible = self._cloud_eligible(authorized)
        print(f"[VisionRouter] Cloud eligible: {eligible} (authorized={authorized})")

        if not eligible:
            return self._analyze_local(image_bytes, task, prompt)

        try:
            if self.cloud_pool is None:
                print("[VisionRouter] Cloud pool is None")
                raise VisionRoutingError(
                    "Cloud vision is enabled, but no cloud vision "
                    "providers are configured."
                )

            print("[VisionRouter] Attempting cloud vision request...")
            text = self.cloud_pool.understand_image(
                image_bytes,
                task=task,
                prompt=prompt,
            )

            if not isinstance(text, str) or not text.strip():
                raise VisionRoutingError(
                    "The cloud vision provider returned empty content."
                )

            provider = ""
            states = getattr(self.cloud_pool, "_states", [])

            for state in states:
                if state.last_success_at > 0 and not state.last_error:
                    provider = state.backend.provider.name

            self.last_result = VisionRoutingResult(
                text=text.strip(),
                route="cloud",
                provider=provider,
            )
            print(f"[VisionRouter] Cloud vision success via {provider}")
            return text.strip()

        except Exception as exc:
            print(f"[VisionRouter] Cloud vision failed: {type(exc).__name__} - {exc}")
            # Do not expose image bytes, API keys, or full request payloads.
            self._record_failure(type(exc).__name__)

            if not self._local_fallback_enabled():
                raise VisionRoutingError(
                    "Cloud vision failed and local fallback is disabled."
                ) from exc

            print("[VisionRouter] Falling back to local vision")
            return self._analyze_local(image_bytes, task, prompt)

    def _cloud_eligible(self, authorized: bool) -> bool:
        cloud_cfg = self.config.get("cloud") or {}

        # DEBUG: Detailed eligibility tracing
        print("[VisionRouter] Checking cloud eligibility...")

        enabled = cloud_cfg.get("enabled", False)
        print(f"  - enabled: {enabled}")
        if not enabled:
            return False

        try:
            consent = self.consent_store.get_consent("vision_cloud")
            print(f"  - consent (vision_cloud): {consent}")
            if not consent:
                return False
        except Exception as e:
            print(f"  - consent check error: {e}")
            return False

        try:
            online = self.health.is_online()
            print(f"  - online: {online}")
            if not online:
                return False
        except Exception as e:
            print(f"  - health check error: {e}")
            return False

        require_preview = cloud_cfg.get("require_preview", True)
        print(f"  - require_preview: {require_preview}, authorized: {authorized}")
        if require_preview and not authorized:
            return False

        pool_exists = self.cloud_pool is not None
        print(f"  - cloud_pool exists: {pool_exists}")
        return pool_exists

    def _local_fallback_enabled(self) -> bool:
        cloud_cfg = self.config.get("cloud") or {}
        return bool(cloud_cfg.get("fallback_to_local", True))

    def _analyze_local(
        self,
        image_bytes: bytes,
        task: str,
        prompt: str,
    ) -> str:
        if self.local_service is None:
            raise VisionRoutingError(
                "Local vision is unavailable and cloud routing "
                "is not permitted or did not succeed."
            )

        try:
            text = self.local_service.analyze(
                image_bytes,
                task=task,
                prompt=prompt,
            )
        except Exception as exc:
            self.last_result = VisionRoutingResult(
                text="",
                route="local",
            )
            raise VisionRoutingError(
                f"Local vision failed ({type(exc).__name__})."
            ) from exc

        if not isinstance(text, str) or not text.strip():
            self.last_result = VisionRoutingResult(
                text="",
                route="local",
            )
            raise VisionRoutingError("Local vision returned no usable content.")

        self.last_result = VisionRoutingResult(
            text=text.strip(),
            route="local",
            provider="moondream",
        )
        return text.strip()

    def _record_failure(self, error_type: str) -> None:
        # Only record a category. Never log image bytes or credentials.
        self.last_result = VisionRoutingResult(
            text="",
            route="cloud_failed",
            provider=error_type,
        )
