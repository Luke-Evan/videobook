{
  description = "VideoBook — 视频转图文电子书流水线的开发环境";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell (let
          # Playwright 自带的 chromium 是上游预编译产物，动态依赖 glib / nss / X11
          # 一整套运行库。NixOS 没有 /usr/lib 兜底，不显式拼进 LD_LIBRARY_PATH 的话
          # 浏览器一启动就以缺 .so 退出（exit 127），capture_frames.py 抓帧与截图
          # 验证都跑不起来。
          # 仅 Linux 需要：darwin 上 xorg.* 等属性不存在，且系统自带框架链。
          browserLibs = pkgs.lib.optionals pkgs.stdenv.isLinux (with pkgs; [
            alsa-lib          # libasound.so.2
            at-spi2-core      # libatk-1.0 / libatspi / libatk-bridge
            cairo
            cups
            dbus
            expat
            glib              # libglib / libgobject / libgio
            libgbm
            libxkbcommon
            nspr
            nss               # libnss3 / libnssutil3 / libsmime3
            pango
            udev              # libudev.so.1
            xorg.libX11
            xorg.libXcomposite
            xorg.libXdamage
            xorg.libXext
            xorg.libXfixes
            xorg.libXrandr
            xorg.libxcb
          ]);
        in {
          packages = [
            pkgs.uv           # 依赖安装 / 锁定（Python 由 uv 按 requires-python 选取）
            pkgs.python312    # requires-python = ">=3.12"
            pkgs.git          # src/publish.py 直接调用 git
          ];

          # uv 装的是 PyPI wheel（ctranslate2 / onnxruntime 等），它们在 NixOS 上
          # 找不到系统 libstdc++，必须显式放进加载路径，否则 faster-whisper import 失败。
          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath ([
            pkgs.stdenv.cc.cc.lib  # libstdc++.so.6
            pkgs.zlib
          ] ++ browserLibs);

          shellHook = ''
            echo "videobook dev shell — uv $(uv --version | cut -d' ' -f2), $(python3.12 --version)"
            echo "  uv sync    # 按 pyproject.toml 安装依赖到 .venv"
            echo "  uv run pytest tests -q"
          '';
        } // pkgs.lib.optionalAttrs pkgs.stdenv.isLinux {
          # chromium 的 PT_INTERP 是 /lib64/ld-linux-x86-64.so.2，在 NixOS 上由 nix-ld
          # 接管、默认落到系统 glibc；而上面的运行库来自 flake 锁定的 nixpkgs，glibc
          # 更新，混用会报 "version `GLIBC_2.4x' not found"。把 nix-ld 的 loader 指向
          # 同一份 nixpkgs 的 ld.so，保证 loader 与库同源（只影响走 nix-ld 的二进制）。
          NIX_LD = "${pkgs.glibc.out}/lib/ld-linux-x86-64.so.2";
        });
      });
    };
}
