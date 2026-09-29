# Vulnerable sample: flask_app

Intentionally vulnerable Flask application used as **ground truth** for the scanner's
tests. It reproduces the source-to-sink chain from the POC spec:

    routes/search.py         request.args["q"]        <- source
        -> services/search_service.py   search_users(q)
            -> database/user_repository.py  execute("... " + q)   <- sink

`find_user_by_id()` in the same repository file is a *safe* parameterized query and acts
as the false-positive control: the pipeline must not report it as Likely Vulnerable.

Never run this application.
