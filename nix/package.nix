{
  pkgs,
  source,
}:
let
  uncomment = import ./uncomment.nix { inherit pkgs; };
in
pkgs.writeShellApplication {
  name = "publicate";
  runtimeInputs = [
    pkgs.gitMinimal
    pkgs.nix
    pkgs.openssh
  ];
  text = ''
    export PUBLICATE_NIX=${pkgs.nix}/bin/nix
    export PUBLICATE_GIT=${pkgs.gitMinimal}/bin/git
    export PUBLICATE_CERT=${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt
    export PUBLICATE_UNCOMMENT=${uncomment}/bin/uncomment
    exec ${pkgs.python3}/bin/python3 ${source}/src/publicate.py "$@"
  '';
}
