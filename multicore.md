# Multicore Conversion Plan

## Goal
Add a simple concurrent conversion option so the app can process multiple images in parallel using 2 or 4 workers.

## User experience
- Add a new `ttk.LabelFrame` titled `"Parallel conversions"` just above the Convert button.
- Label: `Concurrent conversions`
- Options: `1 (sequential)`, `2`, `4`
- Default: `2`
- `1` acts as the sequential fallback for users with very large images or limited RAM.

## Behavior
- Conversion still runs in the background.
- When user starts a conversion, the app dispatches files to a fixed-size worker pool.
- Each worker processes one file at a time.
- Progress is aggregated across all workers.

## Implementation steps

### 1. UI state and control
- Add a new `tk.IntVar`, e.g. `self._worker_count`, default `2`.
- Add radio buttons with options `1 (sequential)`, `2`, `4` inside `_frm_workers` (a new `ttk.LabelFrame`).
- Disable the control during active conversion; re-enable on completion.
- Place `_frm_workers` in `_apply_mode_layout()` just above the Convert button.

### 2. Default and validation
- Ensure the selected worker count is one of `1`, `2`, or `4`.
- If an unexpected value is somehow present, clamp to `2`.

### 3. Worker pool construction
- Replace the current single-thread conversion dispatch with `concurrent.futures.ThreadPoolExecutor`.
- Use `max_workers=self._worker_count.get()`.
- Submit tasks for each source file.

### 4. Task function
- Extract per-file conversion logic into a dedicated helper like `_convert_file(src, dst, ...)`.
- Keep the actual work unchanged:
  - compute destination path
  - choose JPEG / JXL path
  - run conversion subprocesses
  - preserve metadata if enabled
- Return success/failure and any error text.

### 5. Progress and UI updates
- Use `concurrent.futures.as_completed()` to collect finished tasks.
- Maintain a shared integer counter `_done_count` and protect it with a `threading.Lock`.
  ```python
  _lock = threading.Lock()
  _done_count = 0

  for future in concurrent.futures.as_completed(futures):
      with _lock:
          _done_count += 1
          count = _done_count
      self.after(0, lambda c=count: self._set_progress(c, total))
  ```
- Keep all Tkinter updates on the main thread via `self.after(...)`.
- Avoid direct UI calls from worker threads.

### 6. Error aggregation
- Collect exceptions from tasks into a shared list.
- After all workers finish, show summary results.

### 7. Resource management
- Keep `max_workers` low to avoid memory/disk overload.
- `2` and `4` are good defaults for Apple Silicon.
- Do not create a worker per file; use a fixed pool.

### 8. Compatibility with existing modes
- The worker pool should work for `file`, `folder`, and `tree` modes.
- In `file` mode, a pool of 2 or 4 will simply process one file and exit.
- In `folder` / `tree`, the pool will stay active until all files are finished.

## Recommended file structure changes
- Add helper `_run_conversion_concurrent(files, quality, effort, ...)`.
- Keep `_run_conversion()` as a simple dispatcher:
  - either sequential for compatibility or
  - call the concurrent version directly.
- Add a helper `_worker_convert_item(args)` if needed for executor submission.

## Notes
- This does not make the app itself multi-threaded for the GUI.
- The work stays isolated in worker threads and subprocesses.
- The biggest practical limit will be disk I/O and the underlying encoder subprocesses.
- `1`, `2`, and `4` are safe options; `4` is the practical max before disk I/O becomes the bottleneck.
- Temp file naming (`tempfile.NamedTemporaryFile`) is already thread-safe — no change needed.
- `exiftool` invocations are separate subprocesses on separate files — safe to run in parallel.
- Cancel/stop during concurrent conversion is deferred to a future improvement.
