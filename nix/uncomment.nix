{ pkgs }:
pkgs.rustPlatform.buildRustPackage rec {
  pname = "uncomment";
  version = "2.11.0";
  src = pkgs.fetchFromGitHub {
    owner = "Goldziher";
    repo = "uncomment";
    tag = "v${version}";
    hash = "sha256-HtMH5h/1eZ6dkpjXFswyT52JlQu3cw+gRuv2u5nJvk4=";
  };
  cargoHash = "sha256-eCwIHrLcWWdRFCndP4aRfgeEF0sC62uhdJCTg+KgUt8=";
  patches = [ ./uncomment-whitespace.patch ];
  doCheck = false;
  meta = {
    description = "Remove source comments using bundled Tree-sitter parsers";
    homepage = "https://github.com/Goldziher/uncomment";
    license = pkgs.lib.licenses.mit;
    mainProgram = "uncomment";
  };
}
