import os
import re
import subprocess
import sys

from setuptools import Extension, setup, find_packages
from setuptools.command.build_ext import build_ext

# Convert distutils Windows platform specifiers to CMake -A arguments
PLAT_TO_CMAKE = {
    'win32': 'Win32',
    'win-amd64': 'x64',
    'win-arm32': 'ARM',
    'win-arm64': 'ARM64',
}

base_path = os.path.abspath(os.path.dirname(__file__))


# A CMakeExtension needs a sourcedir instead of a file list.
# The name must be the _single_ output extension from the CMake build.
# If you need multiple extensions, see scikit-build.
class CMakeExtension(Extension):
    def __init__(self, name, sourcedir=''):
        Extension.__init__(self, name, sources=[])
        self.sourcedir = os.path.abspath(sourcedir)


class CMakeBuild(build_ext):
    def build_extension(self, ext):
        extdir = os.path.abspath(os.path.dirname(self.get_ext_fullpath(ext.name)))

        # required for auto-detection & inclusion of auxiliary 'native' libs
        if not extdir.endswith(os.path.sep):
            extdir += os.path.sep

        debug = int(os.environ.get('DEBUG', 0)) if self.debug is None else self.debug
        cfg = 'Debug' if debug else 'Release'

        # CMake lets you override the generator - we need to check this.
        # Can be set with Conda-Build, for example.
        cmake_generator = os.environ.get('CMAKE_GENERATOR', '')

        # Set Python_EXECUTABLE instead if you use PYBIND11_FINDPYTHON
        # EXAMPLE_VERSION_INFO shows you how to pass a value into the C++ code
        # from Python.
        cmake_args = [
            f'-DCMAKE_LIBRARY_OUTPUT_DIRECTORY={extdir}',
            f'-DPYTHON_EXECUTABLE={sys.executable}',
            f'-DCMAKE_BUILD_TYPE={cfg}',  # not used on MSVC, but no harm
        ]

        manylinux_inside = os.environ.get('MANYLINUX_INSIDE')
        if manylinux_inside:
            # using gcc 7.5 instead of default (Debian 9) 6.3
            cmake_args.extend([
                '-DCMAKE_C_COMPILER=/usr/local/bin/gcc',
                '-DCMAKE_CXX_COMPILER=/usr/local/bin/g++',
            ])

        build_args = []
        # Adding CMake arguments set as environment variable
        # (needed e.g. to build for ARM OSx on conda-forge)
        if 'CMAKE_ARGS' in os.environ:
            cmake_args += [item for item in os.environ['CMAKE_ARGS'].split(' ') if item]

        # In this example, we pass in the version to C++. You might not need to.
        # cmake_args += [f'-DEXAMPLE_VERSION_INFO={self.distribution.get_version()}']

        if self.compiler.compiler_type != 'msvc':
            # Using Ninja-build since it a) is available as a wheel and b)
            # multithreads automatically. MSVC would require all variables be
            # exported for Ninja to pick it up, which is a little tricky to do.
            # Users can override the generator with CMAKE_GENERATOR in CMake
            # 3.15+.
            if not cmake_generator:
                try:
                    import ninja  # noqa: F401

                    cmake_args += ['-GNinja']
                except ImportError:
                    pass

        else:

            # Single config generators are handled 'normally'
            single_config = any(x in cmake_generator for x in {'NMake', 'Ninja'})

            # CMake allows an arch-in-generator style for backward compatibility
            contains_arch = any(x in cmake_generator for x in {'ARM', 'Win64'})

            # Specify the arch if using MSVC generator, but only if it doesn't
            # contain a backward-compatibility arch spec already in the
            # generator name.
            if not single_config and not contains_arch:
                cmake_args += ['-A', PLAT_TO_CMAKE[self.plat_name]]

            # Multi-config generators have a different way to specify configs
            if not single_config:
                cmake_args += [
                    f'-DCMAKE_LIBRARY_OUTPUT_DIRECTORY_{cfg.upper()}={extdir}'
                ]
                build_args += ['--config', cfg]

        if sys.platform.startswith('darwin'):
            # Cross-compile support for macOS - respect ARCHFLAGS if set
            archs = re.findall(r'-arch (\S+)', os.environ.get('ARCHFLAGS', ''))
            if archs:
                cmake_args += ['-DCMAKE_OSX_ARCHITECTURES={}'.format(';'.join(archs))]

        # Set CMAKE_BUILD_PARALLEL_LEVEL to control the parallel build level
        # across all generators.
        if 'CMAKE_BUILD_PARALLEL_LEVEL' not in os.environ:
            # self.parallel is a Python 3 only way to set parallel jobs by hand
            # using -j in the build_ext call, not supported by pip or PyPA-build.
            if hasattr(self, 'parallel') and self.parallel:
                # CMake 3.12+ only.
                build_args += [f'-j{self.parallel}']

        if not os.path.exists(self.build_temp):
            os.makedirs(self.build_temp)

        subprocess.check_call(
            ['cmake', ext.sourcedir] + cmake_args, cwd=self.build_temp
        )
        subprocess.check_call(
            ['cmake', '--build', '.'] + build_args, cwd=self.build_temp
        )


with open(os.path.join(base_path, 'CMakeLists.txt'), 'r', encoding='utf-8') as f:
    regex = re.compile(r'VERSION "([A-Za-z0-9.]+)"$', re.MULTILINE)
    version = re.findall(regex, f.read())[0]

    if version.count('.') == 3:
        major, minor, path_, tweak = version.split('.')
        version = f'{major}.{minor}.{path_}.dev{tweak}'

with open(os.path.join(base_path, 'README.md'), 'r', encoding='utf-8') as f:
    readme = f.read()

setup(
    name='wrtc',    # webrtc for some reasons isn't allowed but looks like free...
    version=version,
    author='Il`ya Semyonov',
    author_email='ilya@marshal.dev',
    license='BSD 3-Clause',
    url='https://github.com/MarshalX/python-webrtc',
    description='a Python extension that provides bindings to WebRTC M92',
    long_description=readme,
    long_description_content_type='text/markdown',
    classifiers=[
        'Development Status :: 1 - Planning',
        'Natural Language :: English',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Operating System :: MacOS',
        'Operating System :: Unix',
        'Topic :: Internet',
        'Topic :: Multimedia',
        'Topic :: Multimedia :: Video',
        'Topic :: Multimedia :: Video :: Capture',
        'Topic :: Multimedia :: Sound/Audio',
        'Topic :: Multimedia :: Sound/Audio :: Capture/Recording',
        'Topic :: Communications',
        'Topic :: Communications :: Internet Phone',
        'Topic :: Communications :: Telephony',
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
        'Programming Language :: C++',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        "Programming Language :: Python :: Implementation",
        "Programming Language :: Python :: Implementation :: CPython",
    ],
    python_requires='~=3.7',
    package_dir={'': 'python-webrtc/python'},
    packages=find_packages(where='python-webrtc/python'),
    ext_modules=[CMakeExtension('wrtc')],
    cmdclass={'build_ext': CMakeBuild},
    zip_safe=False,
    project_urls={
        'Author': 'https://github.com/MarshalX',
        'Tracker': 'https://github.com/MarshalX/python-webrtc/issues',
        'Source': 'https://github.com/MarshalX/python-webrtc',
    }
)
