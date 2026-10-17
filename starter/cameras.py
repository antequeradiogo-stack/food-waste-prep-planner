"""Camera helpers. In the demo, real CCTV is not connected.

grab_rtsp_frame() grabs ONE frame from an IP camera if OpenCV is installed
(pip install opencv-python-headless). Frames are returned in memory only, never stored.
"""
from PIL import Image

ALLOWED_PREFIXES = ("rtsp://", "http://", "https://")


def grab_rtsp_frame(url: str, timeout_ms: int = 5000):
    """Return (PIL image or None, message)."""
    url = (url or "").strip()
    if not url.startswith(ALLOWED_PREFIXES):
        return None, "Enter a camera URL starting with rtsp://, http:// or https://"
    try:
        import cv2  # optional dependency
    except ImportError:
        return None, ("OpenCV is not installed, so live IP-camera snapshots are off in this demo. "
                      "Install `opencv-python-headless` to enable it, or use upload / device camera.")
    cap = cv2.VideoCapture(url)
    try:
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok or frame is None:
        return None, "Could not read a frame from that camera (check URL, network and credentials)."
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), "Grabbed one frame (not stored)."
