# worker-py

`worker-py` is the Python worker service in `fishRadar2`.

## Responsibilities

- Xianyu scraping
- Product image download
- AI text/image analysis
- Result persistence
- Task execution and failure protection

## Current state

This directory is the first migration cut from the legacy repository. The goal is to preserve the existing scraping and AI pipeline first, then gradually remove web-facing responsibilities as they move to `services/api-go`.
