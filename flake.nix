{
  description = "Prometheus exporter for LLM subscription usage and quota windows";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      overlay = final: _prev: {
        llm-quota-exporter = final.callPackage ./nix/package.nix { };
      };
    in
    {
      overlays.default = overlay;

      # Defaults the service package to this flake's own build for the host's
      # system, so consumers don't have to add the overlay. Works whether pkgs
      # is instantiated by the module system or supplied externally (colmena,
      # flake-parts) — we never touch nixpkgs.overlays.
      nixosModules.default = { pkgs, lib, ... }: {
        imports = [ ./nix/module.nix ];
        services.llm-quota-exporter.package =
          lib.mkDefault self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      };
    }
    // flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; overlays = [ overlay ]; };
      in
      {
        packages.default = pkgs.llm-quota-exporter;
        packages.llm-quota-exporter = pkgs.llm-quota-exporter;

        devShells.default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: with ps; [ prometheus-client httpx pytest ]))
            pkgs.ruff
            pkgs.uv
          ];
        };

        checks.default = pkgs.llm-quota-exporter;
      });
}
