# UIA Test Fixtures

Pre-recorded UI Automation trees from real applications (Phase 3.5).

## Applications to capture

- Chrome / Edge (browser)
- VS Code (editor)
- Word (document)
- Explorer (file manager)
- Terminal (fallback to OCR)

Each capture is a JSON dump of the UIA tree with node properties:
name, control_type, is_password, bounding_rect, children.