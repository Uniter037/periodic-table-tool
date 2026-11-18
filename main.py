"""Default desktop v2 entry; agent requests bypass all GUI imports."""
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

from ui.workbench_v2 import App, main

if __name__ == "__main__":
    main()
