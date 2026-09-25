# Build the standalone SigIQ.exe. Run from the repo root:
#   pwsh packaging/build_exe.ps1
# Output lands in dist/SigIQ.exe (build/ and dist/ are gitignored).
& "C:\Users\acer\anaconda3\envs\iqfile\python.exe" -m PyInstaller packaging/SigIQ.spec --distpath dist --workpath build
