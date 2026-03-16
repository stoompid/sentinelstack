Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "c:\Users\vnguy\OneDrive\Desktop\threatradius\sentinelstack"
WshShell.Run """c:\Users\vnguy\AppData\Local\Programs\Python\Python312\Scripts\uvicorn.exe"" api.main:app --port 8000", 0, False