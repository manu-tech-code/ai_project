#!/usr/bin/env bash
set -e
uvicorn app.main:app --reload --app-dir backend
