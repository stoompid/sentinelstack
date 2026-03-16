@echo off
cd /d "c:\Users\vnguy\OneDrive\Desktop\threatradius\sentinelstack"
"c:\Users\vnguy\AppData\Local\Programs\Python\Python312\Scripts\uvicorn.exe" api.main:app --port 8000