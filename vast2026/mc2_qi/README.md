## Environment

The Python scripts use standard Python libraries:

* json
* datetime
* collections

Place the following files in the same directory:

- index.html

- events_for_trace.json

- level1_department_pairs.json

- level2_receiver_sets.json

- aggregate.py

- stats.py

## Run

Start a local HTTP server from this folder:

python aggregate.py
python -m http.server 8000

Then open:
http://localhost:8000/index.html