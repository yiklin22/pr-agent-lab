"""Stand-in for a model API, used only to rehearse the Step 1 pipeline without an API key.

It speaks just enough of the OpenAI chat-completions protocol for LiteLLM to accept it. Every
request body is saved to disk so the exact prompt PR-Agent sends can be inspected. The reply is a
fixed, clearly labelled review. Nothing it returns is a model result: the "usage" numbers are
characters divided by four, sent only so the accounting path has something to carry.

Usage: python stub_llm.py <port> <capture_dir>
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

STUB_REVIEW = """```yaml
review:
  estimated_effort_to_review_[1-5]: 1
  relevant_tests: |
    No
  key_issues_to_review:
    - relevant_file: |
        STUB
      issue_header: |
        STUB OUTPUT - NOT A MODEL REVIEW
      issue_content: |
        This finding was returned by scripts/stub_llm.py to rehearse the pipeline. No model was called.
      start_line: 1
      end_line: 1
  security_concerns: |
    No
```"""


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


class Handler(BaseHTTPRequestHandler):
    capture_dir: Path

    def log_message(self, *args):  # keep the terminal quiet; requests are saved to disk instead
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            request = {"unparsed": body.decode("utf-8", "replace")}
        index = len(list(self.capture_dir.glob("request_*.json"))) + 1
        (self.capture_dir / f"request_{index:03d}.json").write_text(
            json.dumps({"path": self.path, "body": request}, indent=2), encoding="utf-8"
        )
        prompt_chars = sum(len(_text_of(m.get("content"))) for m in request.get("messages", []))
        prompt_tokens = prompt_chars // 4
        completion_tokens = len(STUB_REVIEW) // 4
        reply = {
            "id": f"stub-{index}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.get("model", "lab-stub"),
            "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": STUB_REVIEW}}
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
        payload = json.dumps(reply).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    port, capture_dir = int(sys.argv[1]), Path(sys.argv[2])
    capture_dir.mkdir(parents=True, exist_ok=True)
    Handler.capture_dir = capture_dir
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
