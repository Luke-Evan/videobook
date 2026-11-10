{
  description = "VideoBook — 视频转图文电子书流水线的开发环境";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.uv           # 依赖安装 / 锁定（Python 由 uv 按 requires-python 选取）
            pkgs.python312    # requires-python = ">=3.12"
            pkgs.git          # src/publish.py 直接调用 git
          ];

          # uv 装的是 PyPI wheel（ctranslate2 / onnxruntime 等），它们在 NixOS 上
          # 找不到系统 libstdc++，必须显式放进加载路径，否则 faster-whisper import 失败。
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.stdenv.cc.cc.lib  # libstdc++.so.6
            pkgs.zlib
          ];

          shellHook = ''
            echo "videobook dev shell — uv $(uv --version | cut -d' ' -f2), $(python3.12 --version)"
            echo "  uv sync    # 按 pyproject.toml 安装依赖到 .venv"
            echo "  uv run pytest tests -q"
          '';
        };
      });
    };
}
