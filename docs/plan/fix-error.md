修复这个报错

Unhandled exception in event loop:
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/asyncio/events.py", line 80, in _run
    self._context.run(self._callback, *self._args)
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/prompt_toolkit/input/vt100.py", line 162, in callback_wrapper
    callback()
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/prompt_toolkit/application/application.py", line 714, in read_from_input_in_context
    context.copy().run(read_from_input)
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/prompt_toolkit/application/application.py", line 694, in read_from_input
    self.key_processor.process_keys()
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/prompt_toolkit/key_binding/key_processor.py", line 273, in process_keys
    self._process_coroutine.send(key_press)
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/prompt_toolkit/key_binding/key_processor.py", line 188, in _process
    self._call_handler(matches[-1], key_sequence=buffer[:])
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/prompt_toolkit/key_binding/key_processor.py", line 323, in _call_handler
    handler.call(event)
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/prompt_toolkit/key_binding/key_bindings.py", line 127, in call
    result = self.handler(event)
             ^^^^^^^^^^^^^^^^^^^
  File "/Users/a58/WorkingSpace/github/blink/src/blink/tui/app.py", line 370, in _
    self._app.layout.focus(self._repo_list_window)
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/site-packages/prompt_toolkit/layout/layout.py", line 136, in focus
    raise ValueError(

Exception Invalid value. Window does not appear in the layout: Window(content=<blink.tui.repo_list.RepoListControl object at 0x107be0b90>)
Press ENTER to continue...
^CException ignored in: <module 'threading' from '/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/threading.py'>
Traceback (most recent call last):
  File "/Library/Frameworks/Python.framework/Versions/3.11/lib/python3.11/threading.py", line 1590, in _shutdown
    lock.acquire()
KeyboardInterrupt: