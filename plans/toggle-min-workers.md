# Toggle Min Workers Feature Plan

## Overview

Add a button to ComfyUI interface that toggles the RunPod endpoint's `min_workers` setting between 0 and 1, allowing users to easily enable/disable an always-on worker without going to the RunPod dashboard.

**Goals:**
- Single-click toggle between `min_workers=0` (cost-saving) and `min_workers=1` (instant response)
- Display current worker state in UI
- Use RunPod's GraphQL API to update endpoint configuration
- Non-invasive implementation in existing custom node

## Phases

### Phase 1: Backend API Route for Worker Toggle

**Files to modify:**
- `/custom_nodes/runpod-queue/__init__.py`

**Implementation:**
1. Add `requests` import (already available in ComfyUI environment)
2. Read `RUNPOD_API_KEY` and `RUNPOD_ENDPOINT_ID` from environment variables
3. Create new route `@server.PromptServer.instance.routes.post('/runpod/toggle_workers')`
4. Implement GraphQL mutation to update endpoint:
   - Query current `workersMin` value
   - Toggle between 0 and 1
   - Return new state to frontend

**GraphQL mutation structure:**
```graphql
mutation {
  saveEndpoint(input: {
    id: "endpoint_id",
    workersMin: 1  # or 0
  }) {
    id
    workersMin
  }
}
```

**Testing:**
- Manually call the route via curl
- Verify endpoint updates in RunPod dashboard
- Test both toggle directions (0→1 and 1→0)

### Phase 2: Backend API Route for Worker Status

**Files to modify:**
- `/custom_nodes/runpod-queue/__init__.py`

**Implementation:**
1. Create new route `@server.PromptServer.instance.routes.get('/runpod/worker_status')`
2. Query RunPod GraphQL API for current endpoint configuration
3. Return `workersMin`, `workersMax`, and active worker count

**GraphQL query structure:**
```graphql
query {
  myself {
    serverlessDiscount {
      discountFactor
      type
    }
    endpoints(input: {id: "endpoint_id"}) {
      id
      workersMin
      workersMax
      idleTimeout
    }
  }
}
```

**Testing:**
- Call route and verify returned data matches dashboard
- Test with different worker states (0 and 1)

### Phase 3: Frontend UI - Status Display and Toggle Button

**Files to modify:**
- `/custom_nodes/runpod-queue/web/runpod_button.js`

**Implementation:**
1. Add worker status indicator to UI (shows current min_workers state)
2. Add "Toggle Min Worker" button next to "Queue on RunPod" button
3. On page load, fetch current worker status via `/runpod/worker_status`
4. Display status: "Min Workers: 0 (Cost Saving)" or "Min Workers: 1 (Always Ready)"
5. On button click:
   - Call `/runpod/toggle_workers`
   - Show loading state
   - Update status display with new value
   - Show success/error notification

**UI Design:**
```
[Queue on RunPod] [Min Workers: 0 ▼]
```

Clicking the worker button toggles between:
- "Min Workers: 0 (Cost Saving)"
- "Min Workers: 1 (Always Ready)"

**Testing:**
- Load ComfyUI and verify status displays correctly
- Click toggle button and verify:
  - Button shows loading state
  - Status updates after toggle
  - RunPod dashboard reflects change

### Phase 4: Error Handling and Edge Cases

**Implementation:**
1. Handle missing environment variables gracefully
2. Handle GraphQL API errors (network, auth, rate limit)
3. Handle concurrent toggle requests (prevent race conditions)
4. Add timeout handling for API calls
5. Display user-friendly error messages

**Edge cases to handle:**
- Missing `RUNPOD_API_KEY`
- Missing `RUNPOD_ENDPOINT_ID`
- Invalid endpoint ID
- API rate limiting
- Network timeout
- Worker already in desired state

**Testing:**
- Test with missing environment variables
- Test with invalid endpoint ID
- Test rapid clicking (concurrent requests)
- Test with network disconnected

## Technical Details

### Environment Variables Required

Add to project `.env` or system environment:
```bash
RUNPOD_API_KEY=your_api_key_here
RUNPOD_ENDPOINT_ID=your_endpoint_id_here
```

These are already used by `scripts/send-to-runpod.py`, so they should exist.

### RunPod GraphQL API

**Endpoint:** `https://api.runpod.io/graphql`

**Authentication:** Bearer token in Authorization header

**Rate Limits:** Unknown, implement exponential backoff

### Data Structures

**Backend response format:**
```json
{
  "status": "success",
  "workers_min": 1,
  "workers_max": 3,
  "message": "Updated min_workers to 1"
}
```

**Error response format:**
```json
{
  "status": "error",
  "message": "Failed to update endpoint: Invalid API key"
}
```

## Alternatives Considered

### Alternative 1: Use runpodctl CLI
**Pros:** No need to implement GraphQL directly
**Cons:** runpodctl doesn't support endpoint configuration updates (only pod management)
**Verdict:** Not feasible

### Alternative 2: Direct REST API
**Pros:** Simpler than GraphQL
**Cons:** RunPod's REST API doesn't support endpoint updates (only GraphQL)
**Verdict:** Not feasible

### Alternative 3: Scheduled Toggle (cron-based)
**Pros:** Could automate based on time of day
**Cons:** Less flexible, requires additional infrastructure
**Verdict:** Could be future enhancement

## Security Considerations

1. **API Key Storage:** Read from environment variable (never hardcode)
2. **Frontend Exposure:** Backend route doesn't expose API key to frontend
3. **Rate Limiting:** Implement client-side debouncing to prevent spam
4. **Error Messages:** Don't expose sensitive info (endpoint IDs, API errors) to frontend

## Implementation Progress

### Phase 1: Backend API Route for Worker Toggle
- [x] Implementation Complete
- [x] Testing Complete

### Phase 2: Backend API Route for Worker Status
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 3: Frontend UI - Status Display and Toggle Button
- [ ] Implementation Complete
- [ ] Testing Complete

### Phase 4: Error Handling and Edge Cases
- [ ] Implementation Complete
- [ ] Testing Complete
