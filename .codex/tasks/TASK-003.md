# TASK-003 — Preserve AI mask options in new-project export

STATUS: VERIFYING
OBJECTIVE: Truyền `mask_method`, `inpaint_engine`, `inpaint_device` từ wizard tạo dự án mới vào `DubRequest` và pipeline, tránh rơi về Boxblur mặc định.
CONTEXT: Root cause đã được duyệt; fix design đã được duyệt tại `.artifacts/bug-fixes/ai-inpaint-method-2-still-boxblur-fix-design.md`.
RELEVANT FILES: `autodub/pipeline.py`, `autodub_gui/pages/new_project_page.py`, `tests/`
DEPENDENCIES: Không.
IMPLEMENTATION INSTRUCTIONS:
- Thêm ba field vào `DubRequest` với default tương thích.
- Thêm ba key vào `NewProjectPage.values()` lấy từ thuộc tính hiện tại, có fallback Settings/default.
- Truyền ba key trong `_build_request()`.
- Thêm regression tests cho AI selection và default/draft cũ; giữ test hiện có.
CONSTRAINTS / DO NOT CHANGE: Không sửa `autodub/media/video.py`, `autodub/media/inpaint/*`, không đổi fallback runtime, không refactor ngoài scope, không commit.
EXPECTED BEHAVIOR: Chọn AI/LaMa/CPU trong wizard tạo request tương ứng; không chọn AI vẫn là blur/lama/auto.
ACCEPTANCE CRITERIA:
- DubRequest expose đúng ba field và backward-compatible defaults.
- values/build_request preserve explicit AI settings.
- Tests cover explicit AI and defaults and pass.
- Existing `tests/test_video_render_inpaint.py` remains green.
TEST COMMANDS: `python -m pytest tests/test_video_render_inpaint.py tests/test_config.py -q` và test mới phù hợp.
UI/UX VERIFICATION STEPS: NOT_APPLICABLE (Codex sẽ kiểm tra propagation bằng tests; UI smoke chỉ khi Antigravity environment cho phép).
ANTIGRAVITY HANDOFF: Gửi handoff deterministic; chỉ thao tác trong workspace hiện tại.
HANDOFF SOURCE: `.codex/evidence/handoff-TASK-003.md` (created by Codex only after STATUS=READY)
EXPECTED EVIDENCE: Changed files, tests/results, blockers, next action, and explicit TASK-003 status markers.
EVIDENCE: `.codex/evidence/handoff-TASK-003.md`; Antigravity edited scoped propagation files and added `tests/test_new_project_mask_propagation.py`. Codex reran scoped suite: 37 passed.
CODEX REVIEW: PENDING
