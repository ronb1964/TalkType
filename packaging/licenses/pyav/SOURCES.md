# PyAV's bundled libraries: licenses and sources

TuxTalk bundles PyAV 16.0.1 (the `cp310-manylinux_2_28_x86_64` wheel). Its
`av.libs/` folder holds 39 shared libraries. Every license file in this folder
is the upstream project's own file, copied unmodified from the source release
named below.

PyAV 16.0.1 gets its FFmpeg from **pyav-ffmpeg release 8.0-2**
(<https://github.com/PyAV-Org/pyav-ffmpeg/releases/tag/8.0-2>, commit
`fab22bcb12748a05f86683ac632fdb96994d970e`), pinned in PyAV's
`scripts/ffmpeg-latest.json` at tag v16.0.1. That release's
`scripts/build-ffmpeg.py` pins each source tarball by SHA256; each tarball
below was downloaded and matched that hash. The build runs with `--community`,
and the build script, the configure flags and the patches it applies to
FFmpeg, GMP, LAME, TwoLAME, libvorbis and libvpx (`patches/`) are at
<https://github.com/PyAV-Org/pyav-ffmpeg/tree/fab22bcb12748a05f86683ac632fdb96994d970e>.
Its FFmpeg patch moves libx264 and libx265 from FFmpeg's GPL list to its
version-3 list, which is why libavcodec reports "LGPL version 3 or later"
while linking two GPL-2.0-or-later libraries; the combination as distributed
is under GPL-3.0-or-later.

The libraries marked *AlmaLinux 8* were not built by pyav-ffmpeg: auditwheel
copied them from the manylinux_2_28 build image (AlmaLinux 8.10) when the
wheel was repaired. Their exact package versions are read from the debug link
inside each file.

| av.libs file(s) | Project | Version | License (SPDX) | License files here | Complete source |
|---|---|---|---|---|---|
| libavcodec .so.62.11.100, libavdevice .so.62.1.100, libavfilter .so.11.4.100, libavformat .so.62.3.100, libavutil .so.60.8.100, libswresample .so.6.1.100, libswscale .so.9.1.100 | FFmpeg | 8.0 (patched by pyav-ffmpeg) | LGPL-3.0-or-later as configured; GPL-3.0-or-later combined with x264/x265 | ffmpeg-LICENSE.md, ffmpeg-COPYING.LGPLv3, ffmpeg-COPYING.GPLv3, ffmpeg-COPYING.LGPLv2.1, ffmpeg-COPYING.GPLv2 | <https://ffmpeg.org/releases/ffmpeg-8.0.tar.xz> + pyav-ffmpeg `patches/ffmpeg.patch` |
| (compiled into libavcodec) | nv-codec-headers | n13.0.19.0 | MIT | `nv-codec-headers-NOTICES` (each header's notice, unmodified: upstream ships no license file) | <https://github.com/FFmpeg/nv-codec-headers/archive/refs/tags/n13.0.19.0.tar.gz> |
| libx264 .so.165 | x264 | git 32c3b801191522961102d4bea292cdb61068d0dd (core 165) | GPL-2.0-or-later | x264-COPYING, x264-AUTHORS | <https://code.videolan.org/videolan/x264/-/archive/32c3b801191522961102d4bea292cdb61068d0dd/x264-32c3b801191522961102d4bea292cdb61068d0dd.tar.bz2> |
| libx265 .so.215 | x265 | 4.1 | GPL-2.0-or-later | x265-COPYING | <https://bitbucket.org/multicoreware/x265_git/downloads/x265_4.1.tar.gz> |
| libaom .so.3.11.0 | libaom | 3.11.0 | BSD-2-Clause, plus the AOM Patent License 1.0; compiled-in third_party code: BSD-3-Clause-Clear (SVT-AV1), BSD-3-Clause (fastfeat, libyuv), MIT (vector), ISC (x86inc) | libaom-LICENSE, libaom-PATENTS, libaom-AUTHORS, libaom-third_party-SVT-AV1-LICENSE.md, libaom-third_party-SVT-AV1-PATENTS.md, libaom-third_party-fastfeat-LICENSE, libaom-third_party-libyuv-LICENSE, libaom-third_party-vector-LICENSE, libaom-third_party-x86inc-LICENSE | <https://storage.googleapis.com/aom-releases/libaom-3.11.0.tar.gz> |
| libdav1d .so.7.0.0 | dav1d | 1.5.1 | BSD-2-Clause | dav1d-COPYING | <https://code.videolan.org/videolan/dav1d/-/archive/1.5.1/dav1d-1.5.1.tar.bz2> |
| libSvtAv1Enc .so.3.1.0 | SVT-AV1 | 3.1.0 | BSD-3-Clause-Clear, plus the AOM Patent License 1.0; compiled-in third_party code: BSD-3-Clause (fastfeat), MIT (safestringlib) | svt-av1-LICENSE.md, svt-av1-PATENTS.md, svt-av1-third_party-fastfeat-LICENSE, svt-av1-third_party-safestringlib-LICENSE | <https://gitlab.com/AOMediaCodec/SVT-AV1/-/archive/v3.1.0/SVT-AV1-v3.1.0.tar.bz2> |
| libvpx .so.11.0.0 | libvpx | 1.15.1 (patched by pyav-ffmpeg) | BSD-3-Clause, plus Google's patent grant; x86inc: ISC | libvpx-LICENSE, libvpx-PATENTS, libvpx-AUTHORS, libvpx-third_party-x86inc-LICENSE | <https://github.com/webmproject/libvpx/archive/v1.15.1.tar.gz> + pyav-ffmpeg `patches/vpx.patch` |
| libwebp .so.7.1.10, libwebpmux .so.3.1.1, libsharpyuv .so.0.1.1 | libwebp | 1.5.0 | BSD-3-Clause, plus Google's patent grant | libwebp-COPYING, libwebp-PATENTS, libwebp-AUTHORS | <https://github.com/webmproject/libwebp/archive/refs/tags/v1.5.0.tar.gz> |
| libopus .so.0.10.1 | Opus | 1.5.2 | BSD-3-Clause | opus-COPYING, opus-AUTHORS | <https://github.com/xiph/opus/releases/download/v1.5.2/opus-1.5.2.tar.gz> |
| libogg .so.0.8.5 | libogg | 1.3.5 | BSD-3-Clause | libogg-COPYING, libogg-AUTHORS | <http://downloads.xiph.org/releases/ogg/libogg-1.3.5.tar.gz> |
| libvorbis .so.0.4.9, libvorbisenc .so.2.0.12 | libvorbis | 1.3.7 (patched by pyav-ffmpeg) | BSD-3-Clause | libvorbis-COPYING, libvorbis-AUTHORS | <https://ftp.osuosl.org/pub/xiph/releases/vorbis/libvorbis-1.3.7.tar.xz> + pyav-ffmpeg `patches/vorbis.patch` |
| libspeex .so.1.5.2 | Speex | 1.2.1 | BSD-3-Clause | speex-COPYING, speex-AUTHORS | <http://downloads.xiph.org/releases/speex/speex-1.2.1.tar.gz> |
| libmp3lame .so.0.0.0 | LAME | 3.100 (patched by pyav-ffmpeg) | LGPL-2.0-or-later | lame-COPYING, lame-LICENSE | <http://deb.debian.org/debian/pool/main/l/lame/lame_3.100.orig.tar.gz> + pyav-ffmpeg `patches/lame.patch` |
| libtwolame .so.0.0.0 | TwoLAME | 0.4.0 (patched by pyav-ffmpeg) | LGPL-2.1-or-later | twolame-COPYING, twolame-AUTHORS | <http://deb.debian.org/debian/pool/main/t/twolame/twolame_0.4.0.orig.tar.gz> + pyav-ffmpeg `patches/twolame.patch` |
| libopencore-amrnb .so.0.0.3, libopencore-amrwb .so.0.0.3 | opencore-amr | 0.1.5 | Apache-2.0 | opencore-amr-LICENSE, opencore-amr-NOTICE | <http://deb.debian.org/debian/pool/main/o/opencore-amr/opencore-amr_0.1.5.orig.tar.gz> |
| libopenh264 .so.2.6.0 | OpenH264 | 2.6.0 | BSD-2-Clause | openh264-LICENSE | <https://github.com/cisco/openh264/archive/refs/tags/v2.6.0.tar.gz> |
| libgnutls .so.30.40.3 | GnuTLS | 3.8.9 (with its included libtasn1) | LGPL-2.1-or-later; compiled-in inih: BSD-3-Clause; CRYPTOGAMS x86 code: BSD-3-Clause, or GPL as that file allows | gnutls-COPYING.LESSERv2, gnutls-AUTHORS, gnutls-lib-inih-LICENSE.txt, gnutls-lib-accelerated-x86-license.txt | <https://www.gnupg.org/ftp/gcrypt/gnutls/v3.8/gnutls-3.8.9.tar.xz> |
| libnettle .so.8.10, libhogweed .so.6.10 | Nettle | 3.10.1 | LGPL-3.0-or-later OR GPL-2.0-or-later | nettle-COPYING.LESSERv3, nettle-COPYINGv3, nettle-COPYINGv2, nettle-AUTHORS | <https://ftp.gnu.org/gnu/nettle/nettle-3.10.1.tar.gz> |
| libgmp .so.10.5.0 | GMP | 6.3.0 (patched by pyav-ffmpeg) | LGPL-3.0-or-later OR GPL-2.0-or-later | gmp-COPYING.LESSERv3, gmp-COPYINGv3, gmp-COPYINGv2, gmp-AUTHORS | <https://ftp.gnu.org/gnu/gmp/gmp-6.3.0.tar.xz> + pyav-ffmpeg `patches/gmp.patch` |
| libunistring .so.5.2.0 | GNU libunistring | 1.3 | LGPL-3.0-or-later OR GPL-2.0-or-later | libunistring-COPYING.LIB, libunistring-COPYING, libunistring-AUTHORS | <https://ftp.gnu.org/gnu/libunistring/libunistring-1.3.tar.gz> |
| libasound .so.2.0.0 | alsa-lib | 1.2.14 | LGPL-2.1-or-later | alsa-lib-COPYING | <https://www.alsa-project.org/files/pub/lib/alsa-lib-1.2.14.tar.bz2> |
| libdrm .so.2.4.0 | libdrm, *AlmaLinux 8* | 2.4.115 (package libdrm-2.4.115-2.el8) | MIT | `libdrm-NOTICES` (the notice of each source file in the library, unmodified: upstream ships no license file) | <https://vault.almalinux.org/8.10/AppStream/Source/Packages/libdrm-2.4.115-2.el8.src.rpm> (upstream: <https://dri.freedesktop.org/libdrm/libdrm-2.4.115.tar.xz>) |
| libxcb .so.1.1.0, libxcb-shape .so.0.0.0, libxcb-shm .so.0.0.0, libxcb-xfixes .so.0.0.0 | libxcb, *AlmaLinux 8* | 1.13.1 (package libxcb-1.13.1-1.el8) | X11 | libxcb-COPYING | <https://vault.almalinux.org/8.10/AppStream/Source/Packages/libxcb-1.13.1-1.el8.src.rpm> (upstream: <https://xcb.freedesktop.org/dist/libxcb-1.13.1.tar.bz2>) |
| libXau .so.6.0.0 | libXau, *AlmaLinux 8* | 1.0.9 (package libXau-1.0.9-3.el8) | MIT-open-group | libXau-COPYING | <https://vault.almalinux.org/8.10/AppStream/Source/Packages/libXau-1.0.9-3.el8.src.rpm> (upstream: <https://www.x.org/releases/individual/lib/libXau-1.0.9.tar.bz2>) |
| libmvec-2 .28.so | GNU C Library (libmvec), *AlmaLinux 8* | 2.28 (package glibc-2.28-251.el8_10.25) | LGPL-2.1-or-later | glibc-COPYING.LIB, glibc-LICENSES | <https://vault.almalinux.org/8.10/BaseOS/Source/Packages/glibc-2.28-251.el8_10.25.src.rpm> (upstream: <https://ftp.gnu.org/gnu/glibc/glibc-2.28.tar.xz>) |

Outside `av.libs`, CTranslate2's wheel bundles
`ctranslate2.libs/libgomp .so.1.0.0`, from GCC 8.5.0 (package
gcc-8.5.0-28.el8_10.alma.1, AlmaLinux 8): GPL-3.0-or-later WITH
GCC-exception-3.1. License files: libgomp-COPYING3, libgomp-COPYING.RUNTIME.
Source: <https://vault.almalinux.org/8.10/BaseOS/Source/Packages/gcc-8.5.0-28.el8_10.alma.1.src.rpm>
(upstream: <https://ftp.gnu.org/gnu/gcc/gcc-8.5.0/gcc-8.5.0.tar.xz>).
