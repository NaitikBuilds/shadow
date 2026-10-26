
from shadow.ui.vision_cloud_preview import (
    VisionCloudDecision,
    VisionCloudPreviewDialog,
)


def test_preview_defaults_to_cancel(qtbot):
    dialog = VisionCloudPreviewDialog(
        image_bytes=b"not-a-valid-image",
        window_title="Example",
        process_name="example.exe",
        provider_name="gemini",
    )
    qtbot.addWidget(dialog)

    assert dialog.decision == VisionCloudDecision.CANCEL
    assert dialog.dont_ask_again is False


def test_preview_local_choice_does_not_authorize_cloud(qtbot):
    dialog = VisionCloudPreviewDialog(
        image_bytes=b"not-a-valid-image",
        window_title="Example",
        process_name="example.exe",
        provider_name="gemini",
    )
    qtbot.addWidget(dialog)

    dialog._use_local()

    assert dialog.decision == VisionCloudDecision.USE_LOCAL
    assert dialog.dont_ask_again is False


def test_preview_send_requires_explicit_action(qtbot):
    dialog = VisionCloudPreviewDialog(
        image_bytes=b"not-a-valid-image",
        window_title="Example",
        process_name="example.exe",
        provider_name="gemini",
    )
    qtbot.addWidget(dialog)

    dialog._send()

    assert dialog.decision == VisionCloudDecision.SEND_TO_CLOUD
