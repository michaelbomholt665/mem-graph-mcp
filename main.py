import sys
import pathlib
from dotenv import load_dotenv

load_dotenv()

# Allow imports from 'src'
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))

from mem_graph.server import run  # noqa: E402

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nServer shut down gracefully.", flush=True)
