SyntaxError: This app has encountered an error. The original error message is redacted to prevent data leaks. Full error details have been recorded in the logs (if you're on Streamlit Cloud, click on 'Manage app' in the lower right of your app).
Traceback:
File "/home/adminuser/venv/lib/python3.13/site-packages/streamlit/runtime/scriptrunner/exec_code.py", line 128, in exec_func_with_error_handling
    result = func()
File "/home/adminuser/venv/lib/python3.13/site-packages/streamlit/runtime/scriptrunner/script_runner.py", line 667, in code_to_exec
    _mpa_v1(self._main_script_path)
    ~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^
File "/home/adminuser/venv/lib/python3.13/site-packages/streamlit/runtime/scriptrunner/script_runner.py", line 165, in _mpa_v1
    page.run()
    ~~~~~~~~^^
File "/home/adminuser/venv/lib/python3.13/site-packages/streamlit/navigation/page.py", line 296, in run
    code = ctx.pages_manager.get_page_script_byte_code(str(self._page))
File "/home/adminuser/venv/lib/python3.13/site-packages/streamlit/runtime/pages_manager.py", line 160, in get_page_script_byte_code
    return self._script_cache.get_bytecode(script_path)
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^
File "/home/adminuser/venv/lib/python3.13/site-packages/streamlit/runtime/scriptrunner/script_cache.py", line 72, in get_bytecode
    filebody = magic.add_magic(filebody, script_path)
File "/home/adminuser/venv/lib/python3.13/site-packages/streamlit/runtime/scriptrunner/magic.py", line 45, in add_magic
    tree = ast.parse(code, script_path, "exec")
File "/usr/local/lib/python3.13/ast.py", line 50, in parse
    return compile(source, filename, mode, flags,
                   _feature_version=feature_version, optimize=optimize)
