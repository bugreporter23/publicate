{
  description = "Publicate: public source views and isolated Nix build verification";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      eachSystem = nixpkgs.lib.genAttrs systems;
    in
    {
      packages = eachSystem (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          source = pkgs.lib.fileset.toSource {
            root = ./.;
            fileset = ./src;
          };
          publicate = import ./nix/package.nix { inherit pkgs source; };
          uncomment = import ./nix/uncomment.nix { inherit pkgs; };
        in
        {
          inherit publicate uncomment;
          default = publicate;
        }
      );
      apps = eachSystem (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.publicate}/bin/publicate";
        };
      });
      lib.mkApp =
        {
          pkgs,
          policy ? null,
          policyFile ? null,
        }:
        assert (policy == null) != (policyFile == null);
        assert policyFile == null || (builtins.isString policyFile && !builtins.hasContext policyFile);
        let
          config =
            if policyFile != null then
              policyFile
            else
              toString (pkgs.writeText "publicate-policy.json" (builtins.toJSON policy));
          command = pkgs.writeShellApplication {
            name = "publicate";
            text = ''
              exec ${
                self.packages.${pkgs.stdenv.hostPlatform.system}.publicate
              }/bin/publicate --policy ${pkgs.lib.escapeShellArg config} "$@"
            '';
          };
        in
        {
          type = "app";
          program = "${command}/bin/publicate";
        };
      devShells = eachSystem (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = [
              pkgs.python3
              pkgs.black
              pkgs.git
              pkgs.ripgrep
              pkgs.nixfmt
              self.packages.${system}.uncomment
            ];
            shellHook = ''
              export PUBLICATE_UNCOMMENT=${self.packages.${system}.uncomment}/bin/uncomment
            '';
          };
        }
      );
    };
}
