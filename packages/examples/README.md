# iCoDer Examples

Multi-language examples for the iCoDer Medical AI Agent Platform.

## Files

| File | Description |
|------|-------------|
| `iCoDer-API.postman_collection.json` | Postman Collection — 115 API endpoints, import into Postman to explore |
| `js/basic.js` | JavaScript SDK — facts extraction, agent streaming |
| `python/basic.py` | Python SDK — client setup, facts, agents, usage |
| `html/stt-demo.html` | Pure HTML with `<icoder-stt>` Web Component |
| `html/assistant-demo.html` | Pure HTML with `<icoder-assistant>` Web Component |

## Quick Start

1. Import `iCoDer-API.postman_collection.json` into Postman
2. Set `base_url` and `access_token` variables
3. Explore any endpoint

Or run examples:

```bash
# JavaScript
cd js && node basic.js

# Python
cd python && pip install icoder-sdk && python basic.py

# HTML — open in browser
open html/stt-demo.html
```
