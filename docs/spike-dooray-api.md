# Dooray API Spike Findings

**Date:** 2026-04-17
**Status:** PENDING — run scripts/spike_dooray.py with real credentials to fill this in

## Auth
- Header format: `Authorization: dooray-api <token>`  ← verify
- Base URL: `https://pycon.dooray.com/common/v1`  ← confirm

## Task Status Strings (workflowClass or workflowId field name)
| Our state | Dooray API value |
|-----------|-----------------|
| NEW | `registered` ← verify |
| REVIEWING | `working` ← verify |
| PAYMENT_PENDING | `???` ← fill in |
| REJECTED | `???` ← fill in |
| COMPLETED | `done` ← verify |

## Task Object Fields
- Task ID field name: `id` or `postId`?  ← fill in
- Status field name: `workflowClass` or `workflowId`?  ← fill in
- Subject field: `subject`?
- Body field: `body.content`?

## Comment Object Fields
- Comment ID field: `id` or `logId`?  ← fill in
- Content field: `body.content`?  ← fill in

## Task Copy Fields (for Step 3 cross-portal copy)
Fields to include when creating a pycon portal task:
- [ ] subject
- [ ] body.content
- [ ] ... (add fields agreed with 파사모 team)

## Amount Format in Task Body
Example body text containing amount:
```
금액: 50,000원  ← paste actual example
```
Regex that matches: `금액[:\s]*([0-9,]+)\s*원`  ← confirm or update
