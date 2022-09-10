import os
import sys
project_path = os.getcwd()
print(project_path)
src_path = os.path.join(
    project_path, "IC"
)
sys.path.append(src_path)
print(src_path)
print(sys.path.append(src_path))
