import os
import shutil


class LambdaTool:
    def __init__(self, code_name: str):
        self.code_name = code_name

    def zip_code(self):
        shutil.make_archive(self.code_name, 'zip',
                            root_dir=self.code_name, verbose=True)

    def install_requirements(self):
        os.system(
            f"python3 -m pip install --target {self.code_name}/lib --requirement {self.code_name}/requirements.txt")
        return


code_name = "stellar_stream/lambda/kstream/dev"
func = LambdaTool(code_name)
# func.install_requirements()
func.zip_code()
