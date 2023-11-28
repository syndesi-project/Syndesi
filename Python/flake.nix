# flake.nix
# Sébastien Deriaz
# 30.09.2023
# This flake is used to provide the Python environment for the syndesi package
{
    description = "Python Syndesi Nix flake";
    
    inputs = {
        nixpkgs.url = "github:nixos/nixpkgs/nixos-23.05";
        flake-utils.url = "github:numtide/flake-utils";
    };

    outputs = { nixpkgs, flake-utils, ... }: flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = import nixpkgs {
        inherit system;
      };
    in
    {
      devShells.default = pkgs.mkShell {
        buildInputs = with pkgs; [
          python310
          (python310.withPackages
            (pkgs: with pkgs; [
              pytest
              pyserial
              pyvisa
            ]))
        ];
      };
    });
}