"""Exercise the real Qt/worker pipeline in a private application directory."""
import os
from pathlib import Path
import sys
import tempfile
import time
from PySide6.QtCore import QTimer


def run_smoke(application, window_class):
    temporary = tempfile.TemporaryDirectory(prefix='ptt-qt-smoke-')
    marker = Path(os.environ.get('PTT_SMOKE_MARKER', str(Path(sys.executable).parent / 'smoke_progress.txt')))
    def log(message):
        with marker.open('a', encoding='utf-8') as stream:
            stream.write(message + '\n')
    log('start')
    window = window_class(user_dir=temporary.name, recover=False)
    log('app_created')
    window.output_dir = os.environ.get('PTT_SMOKE_EXPORT_DIR', str(Path(temporary.name) / 'output'))
    window.demo()
    started = time.monotonic()
    phase = ['preview']
    formats = iter(('svg', 'png', 'pdf'))
    timer = QTimer()
    timer.setInterval(100)
    failed = [False]
    def finish(error=None):
        timer.stop()
        failed[0] = error is not None
        log('smoke:failed:' + str(error) if error else 'smoke:passed')
        window.shutdown()
        application.quit()
    def check():
        try:
            if time.monotonic() - started > 150:
                raise RuntimeError('Qt smoke timed out: ' + window.status.text())
            if window.status.text().startswith('未完成：'):
                raise RuntimeError(window.status.text())
            ready = (window.preview.source_image is not None and not window.preview.is_stale) if phase[0] == 'preview' else (window.last_output and Path(window.last_output).is_file())
            if not ready:
                return
            if phase[0] == 'preview':
                log('preview:passed')
                from core.reference_image import load_reference_image
                source = Path(temporary.name) / 'reference.svg'
                source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect width="40" height="20" fill="red"/></svg>', encoding='utf-8')
                image = load_reference_image(source)
                assert image.size == (40, 20)
                image.close()
                log('reference:passed')
            else:
                log('export:' + phase[0])
            phase[0] = next(formats, None)
            if phase[0] is None:
                finish()
                return
            window.last_output = None
            window.output_format = phase[0]
            window.export()
        except Exception as exc:
            finish(exc)
    timer.timeout.connect(check)
    timer.start()
    log('before_mainloop')
    application.exec()
    log('after_mainloop')
    temporary.cleanup()
    return 2 if failed[0] else 0
