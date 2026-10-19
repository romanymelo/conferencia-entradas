import sys
from pathlib import Path

import pytest

import main


class _Fluxo:
    def __init__(self, falha=False):
        self.chamadas = []
        self.falha = falha

    def reconfigure(self, **kw):
        if self.falha:
            raise ValueError("x")
        self.chamadas.append(kw)


def _congela(monkeypatch, exe):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))


def _sem_pausa(monkeypatch):
    pausas = []
    monkeypatch.setattr(main, "_pausa", lambda: pausas.append(1))
    return pausas


def test_nao_congelado_nao_pausa_nem_cria_pasta(monkeypatch, tmp_path):
    pausas = _sem_pausa(monkeypatch)
    cod = main.principal(["--entrada", str(tmp_path / "nada"), "--saida", str(tmp_path / "s")])
    assert cod == main.CODIGO_ENTRADA_INVALIDA
    assert pausas == []
    assert not (tmp_path / "nada").exists()


def test_congelado_cria_entrada_ao_lado_do_exe_e_avisa(monkeypatch, tmp_path, capsys):
    _congela(monkeypatch, tmp_path / "conferencia-entradas.exe")
    pausas = _sem_pausa(monkeypatch)
    monkeypatch.chdir(Path(__file__).parent)  # cwd diferente do exe
    assert main.principal([]) == 0
    assert (tmp_path / "entrada").is_dir()
    assert not (tmp_path / "saida").exists()
    assert "Coloque nela os PDFs" in capsys.readouterr().out
    assert pausas == [1]


def test_congelado_entrada_explicita_vence_o_padrao(monkeypatch, tmp_path):
    _congela(monkeypatch, tmp_path / "x.exe")
    _sem_pausa(monkeypatch)
    vistos = []
    monkeypatch.setattr(main, "executa", lambda e, s: vistos.append((e, s)) or 3)
    outra, saida = tmp_path / "outra", tmp_path / "out"
    outra.mkdir()
    assert main.principal(["--entrada", str(outra), "--saida", str(saida)]) == 3
    assert vistos == [(outra, saida)]


def test_congelado_padroes_ao_lado_do_exe(monkeypatch, tmp_path):
    _congela(monkeypatch, tmp_path / "x.exe")
    _sem_pausa(monkeypatch)
    (tmp_path / "entrada").mkdir()
    vistos = []
    monkeypatch.setattr(main, "executa", lambda e, s: vistos.append((e, s)) or 0)
    main.principal([])
    assert vistos == [(tmp_path / "entrada", tmp_path / "saida")]


def test_congelado_pausa_mesmo_com_erro_e_limita_codigo(monkeypatch, tmp_path):
    _congela(monkeypatch, tmp_path / "x.exe")
    pausas = _sem_pausa(monkeypatch)
    (tmp_path / "entrada").mkdir()
    monkeypatch.setattr(main, "executa", lambda e, s: 500)
    assert main.principal([]) == main.LIMITE_CODIGO_SAIDA
    monkeypatch.setattr(main, "executa", lambda e, s: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        main.principal([])
    assert pausas == [1, 1]


def test_pausa_tolera_stdin_indisponivel(monkeypatch):
    def sem_stdin(_=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", sem_stdin)
    main._pausa()  # não levanta


def test_console_utf8_e_tolera_fluxo_sem_reconfigure(monkeypatch):
    out, err = _Fluxo(), _Fluxo(falha=True)
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    main._configura_console()
    assert out.chamadas == [{"encoding": "utf-8", "errors": "replace"}]
    monkeypatch.setattr(sys, "stdout", object())
    main._configura_console()  # sem reconfigure: não levanta
