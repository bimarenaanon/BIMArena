---
name: delete_element
description: Delete an existing Revit element — verify the selection names the intended element first; a deleted wall or level takes everything hosted on it.
software: Revit
---

# Delete an element (capability)

1. Select the element (`select-element`, see `the application basics`) — ⚠️ verify the status bar
   names the INTENDED element before deleting; there is no dialog to save you.
2. Press **Delete** (or right-click → **Delete**).
3. **Esc** to clear.

## Common warnings

- ⚠️ Deleting a LEVEL deletes its views and everything hosted on it — never a casual delete.
- A deleted-by-mistake element: Ctrl+Z immediately.

## Verification

The right element is gone, and nothing that had to stay went with it (a
deleted wall takes its hosted doors/windows and can un-bound a room — re-create such
collateral losses). That is the whole check — verify nothing else.
