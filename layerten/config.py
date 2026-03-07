import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "")

TARGET_REPO = "567-labs/instructor"
REPO_OWNER, REPO_NAME = TARGET_REPO.split("/")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPO_CLONE_DIR = DATA_DIR / "repo"
RAW_EVENTS_DIR = DATA_DIR / "raw_events"
RAW_EVENTS_PATH = RAW_EVENTS_DIR / "events.jsonl"
CHECKPOINT_PATH = DATA_DIR / "checkpoint.json"

UNIFIED_DIR = DATA_DIR / "unified"
UNIFIED_EVENTS_PATH = UNIFIED_DIR / "events.jsonl"
UNIFIED_TIMELINE_PATH = UNIFIED_DIR / "timeline.jsonl"
UNIFIED_PERSONS_PATH = UNIFIED_DIR / "persons.json"
UNIFIED_BRANCHES_PATH = UNIFIED_DIR / "branches.json"
UNIFIED_LABELS_PATH = UNIFIED_DIR / "labels.json"
UNIFIED_RENAMES_PATH = UNIFIED_DIR / "renames.json"
UNIFIED_FILE_TREE_PATH = UNIFIED_DIR / "file_tree.json"
MERGE_LOG_PATH = UNIFIED_DIR / "merge_log.jsonl"
UNIFIED_INDEX_PATH = UNIFIED_DIR / "index.json"

NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
PROCESS_CHECKPOINT_PATH = DATA_DIR / "process_checkpoint.json"
