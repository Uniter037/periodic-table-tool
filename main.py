"""Qt desktop entry; agent requests bypass GUI, --ui=tk is a migration fallback."""
import multiprocessing

# PyInstaller worker dispatch must precede agent parsing and GUI imports.
if __name__ == "__main__":
    multiprocessing.freeze_support()

import sys

if __name__ == "__main__" and any(
    arg == "--agent-request" or arg.startswith("--agent-request=")
    for arg in sys.argv[1:]
):
    from application.agent_api import main as agent_main
    raise SystemExit(agent_main())

if '--ui=tk' in sys.argv[1:]:
    from ui.workbench_v2 import App, main
else:
    from ui.qt.workbench import MainWindow as App, main

if __name__ == "__main__":
    raise SystemExit(main())
