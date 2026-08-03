{ lib, python3Packages }:

python3Packages.buildPythonApplication {
  pname = "llm-quota-exporter";
  version = "0.1.0";
  pyproject = true;

  src = lib.cleanSourceWith {
    src = ../.;
    filter = path: type:
      let base = baseNameOf path;
      in !(lib.elem base [ ".venv" ".ruff_cache" ".pytest_cache" "__pycache__" "result" "dist" "build" ])
         && lib.cleanSourceFilter path type;
  };

  build-system = [ python3Packages.hatchling ];

  dependencies = with python3Packages; [
    prometheus-client
    httpx
  ];

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];
  pythonImportsCheck = [ "llm_quota_exporter" ];

  meta = with lib; {
    description = "Prometheus exporter for LLM subscription usage and quota windows";
    homepage = "https://github.com/georgewhewell/quota-exporter";
    license = licenses.mit;
    mainProgram = "llm-quota-exporter";
    maintainers = [ ];
  };
}
