Set sh = CreateObject("Wscript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
sh.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = sh.CurrentDirectory & "\.venv\Scripts\pythonw.exe"
sh.Run """" & pythonw & """ main.py", 0, False
