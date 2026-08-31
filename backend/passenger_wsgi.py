import os
import traceback
import sys
import glob

# Passenger automatically handles the cPanel virtual environment.
# We do not need to manually add .venv to sys.path, and doing so can cause
# it to forcefully load incompatible Windows binaries if the local .venv was uploaded.

# Add project directory to Python path
base_dir = os.path.dirname(__file__)
sys.path.insert(0, base_dir)

def application(environ, start_response):
    try:
        from app import app as _application
        return _application(environ, start_response)
    except Exception:
        err_msg = "Web App Startup Error:\n\n" + traceback.format_exc()
        try:
            error_log_path = os.path.join(base_dir, "fatal_startup_error.txt")
            with open(error_log_path, "w") as f:
                f.write(err_msg)
        except Exception:
            pass
            
        start_response('200 OK', [('Content-type', 'text/plain')])
        return [err_msg.encode('utf-8')]
