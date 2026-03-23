```
PRVVSTATS(1)                    User Commands                    PRVVSTATS(1)

NAME
       prvvstats - Paraver trace statistical analysis tool

SYNOPSIS
       python prvvstats.py trace.prv [--event-type N] [--output FILE]
                                     [--llm-output FILE]

DESCRIPTION
       prvvstats reads a Paraver trace set (.prv, .pcf, .row) and
       reconstructs the execution intervals of a selected event type.
       For each interval the tool records the executing thread, start and
       end timestamps (nanoseconds), and duration.  From these intervals it
       computes per-thread and global duration statistics and generates a
       two-panel figure.

       An optional LLM-friendly text export (--llm-output) renders the full
       analysis as a structured plain-text document suitable for ingestion
       by large language models.  For traces shorter than approximately five
       seconds the export is lossless: every interval appears verbatim.

       The primary use case is analysing nOS-V task execution in
       OVNI-generated traces, but any event type present in the PCF can be
       selected.

OPTIONS
       trace.prv
              Path to the Paraver trace file.  The companion .pcf and .row
              files are resolved automatically from the same directory and
              base name.  Both are optional; if absent, event values and
              thread names are shown as integers.

       --event-type N
              Numeric event type ID to analyse.  Defaults to 11 (nOS-V task
              type of the running thread).  Available IDs and their labels
              are listed in the EVENT_TYPE sections of the .pcf file.

       --output FILE
              Path for the output figure.  Accepts any extension supported
              by matplotlib (.png, .pdf, .svg, ...).  Defaults to stats.png
              in the current directory.

       --llm-output FILE
              Write the LLM-friendly text export to FILE.  Use - to print
              to standard output.  If omitted, no LLM export is produced.

INPUT FILES
       All three Paraver files must share the same base name and directory.

       trace.prv
              Event records.  One record per line in the format:

                2:cpu:appl:task:thread:time_ns:type:value[:type:value ...]

              The first line is the header:

                #Paraver (date):DURATION_ns:0:1:1(NROWS:0)

              Lines beginning with # are comments or metadata and are
              skipped.  A value of 0 signals the end of an event interval;
              any other value signals a start or type change.

       trace.pcf
              Event type and value definitions.  Structured in sections:

                EVENT_TYPE
                  color  type_id  label
                VALUES
                  value_id  name
                  ...

              An empty line separates sections.

       trace.row
              Thread name list.  Format:

                LEVEL THREAD SIZE N
                name_of_row_1
                name_of_row_2
                ...

              Row names are 1-indexed and correspond to the thread field in
              .prv records.

OUTPUT
   Standard output
       Two statistics tables are printed after parsing completes.

       GLOBAL STATISTICS  All intervals pooled across threads, grouped by
       task name and sorted by pct_timeline descending.

         task           Task name from the PCF, or the raw integer value
                        if the PCF is absent or lacks a VALUES entry.

         mean_ms        Arithmetic mean of interval durations (ms).

         median_ms      Median interval duration (ms).

         p25_ms         25th percentile duration (ms).

         p75_ms         75th percentile duration (ms).

         count          Number of intervals observed across all threads.

         pct_timeline   sum(durations) / (trace_duration x nthreads) x 100.
                        Fraction of total available CPU-time consumed by
                        this task type.

       PER-THREAD STATISTICS  Same columns, grouped by (thread, task).
       pct_timeline is relative to a single thread's timeline:
       sum(durations_on_thread) / trace_duration x 100.

   Figure
       The figure contains two panels stacked vertically.

       Top panel - violin plots
              One violin per task type.  The body shows the full
              distribution of interval durations in milliseconds.  A white
              dot marks the mean.  Wider sections indicate higher density
              at that duration.

              Useful for: identifying tasks with consistent duration
              (narrow violin), high variance or multi-modal distributions
              (wide or split violin), and outlier intervals at the tails.

       Bottom panel - stacked horizontal bar chart
              One bar per thread.  Each segment corresponds to a task type
              and is sized by its pct_timeline on that thread.  The colour
              legend is shared with the top panel.

              Useful for: detecting load imbalance (bars of different total
              length), threads dominated by a single task, and idle threads
              (short total bar).

   LLM export (--llm-output)
       The export is a plain-text document structured in five sections.

       TRACE header
              Trace filename, duration, thread count, interval count, and
              event type label.  A warning is embedded here if the
              estimated file size exceeds 600 KB.

       TASK LEGEND
              Maps single-character abbreviations to full task names.  The
              top five tasks by pct_timeline receive uppercase letters
              (M, S, D, W, A); the next five receive lowercase (a-e);
              remaining tasks appear in [brackets] in the sequences.

       GLOBAL STATS
              The global statistics table formatted to two decimal places.

       PER-THREAD STATS
              The per-thread statistics table (equivalent to the violin
              plot data), formatted to two decimal places.  Columns:
              thread, task, mean_ms, median_ms, p25_ms, p75_ms, count,
              pct_timeline.

       THREAD SEQUENCES
              One line per thread:

                THREAD [busy=X%]: TOK TOK TOK ...

              Each token has the form ABBREV@start_ms(duration_ms).  Idle
              gaps larger than 0.1 ms are represented as .@start(dur).
              Start times are relative to the first event in the trace.

EXAMPLES
       Analyse nOS-V task types with default settings:

              python prvvstats.py cpu.chop1.prv

       Save the figure in PDF format:

              python prvvstats.py cpu.chop1.prv --output report.pdf

       Analyse subsystem events (type 13) and save the figure:

              python prvvstats.py cpu.chop1.prv --event-type 13 \
                      --output subsys.png

       Generate an LLM export from a short trace:

              python prvvstats.py cpu.chop1.prv --llm-output trace.txt

       Print the LLM export to stdout and pipe to a pager:

              python prvvstats.py cpu.chop1.prv --llm-output - | less -S

       Redirect the statistics tables to a file:

              python prvvstats.py cpu.chop1.prv > report.txt

NOTES
   Recommended trace length for LLM export
       For a 48-second, 97-thread trace the LLM export is approximately
       7 MB (~1.7 M tokens), which exceeds most model context windows.
       Chopping the trace to under five seconds (roughly 40 CG iterations
       in HPCCG) reduces the export to approximately 700 KB (~175 K
       tokens), which fits comfortably in current large-context models.
       Use the Paraver Cutter or ovni-cutter to extract a representative
       window before invoking --llm-output.

   nOS-V / HPCCG task names
       Common event type IDs in OVNI-generated traces:

         10   nOS-V task id of the RUNNING thread
         11   nOS-V task type of the RUNNING thread  (default)
         12   nOS-V task body source
         13   nOS-V subsystem

       Typical task names for HPCCG:

         HPC_sparsemv_range           Sparse matrix-vector multiply.
                                      Dominant compute kernel.
         _waxpby_range_beta           Vector update (WAXPBY).
         _waxpby_range_negative_beta  Vector update with negated beta.
         _ddot_range_xy               Dot product of two vectors.
         _ddot_range_xx               Dot product of a vector with itself.
         MPI_Allreduce_*              MPI collective wrapped as a task.
         compute_beta                 Scalar reduction (beta coefficient).
         compute_normr_*              Norm reduction.

       A high pct_timeline for HPC_sparsemv_range indicates a
       compute-bound run dominated by the SpMV kernel, which is expected.

DIAGNOSTICS
       No intervals found. Check --event-type value.
              The selected event type has no non-zero values in the trace,
              or the type ID does not exist.  Inspect the .pcf file for
              valid EVENT_TYPE sections and pass the correct ID with
              --event-type.

       Task names appear as large integers
              The .pcf file is absent or the event type's VALUES section is
              missing.  The tool still runs; labels default to raw numeric
              value IDs.

       WARNING: estimated output ~N KB
              The LLM export exceeds 600 KB.  The file is still written.
              Consider shortening the trace; see NOTES above.

FILES
       trace.prv        Paraver event records (required).
       trace.pcf        Event type and value labels (optional).
       trace.row        Thread name list (optional).
       stats.png        Default figure output path.
       requirements.txt numpy, pandas, matplotlib.

SEE ALSO
       paraver(1), ovni(1)

       Paraver trace format reference:
       https://tools.bsc.es/paraver

       OVNI instrumentation library:
       https://github.com/bsc-pm/ovni

AUTHORS
       prv-vstats was written for BSC performance analysis of nOS-V / HPCCG
       task-based workloads.

prvvstats 1.0                    2026-03-23                      PRVVSTATS(1)
```
