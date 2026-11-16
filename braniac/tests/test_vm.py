from braniac import vm


def test_estado_sem_virtualbox_ou_vm(monkeypatch):
    monkeypatch.setattr(vm, "_vb", lambda *a, **k: (1, "nao existe"))
    assert vm.estado() == "inexistente"
    assert vm.criar("x.iso") != "A VM ja existe."


def test_estado_le_vmstate(monkeypatch):
    monkeypatch.setattr(vm, "_vb", lambda *a, **k: (0, 'name="x"\nVMState="running"\n'))
    assert vm.estado() == "running"
    assert vm.ligar() == "Ja esta ligada."


def test_criar_isola_a_vm(monkeypatch, tmp_path):
    monkeypatch.setattr(vm, "DADOS", tmp_path)
    monkeypatch.setattr(vm, "PASTA", tmp_path / "vm")
    chamadas = []

    def falso(*a, **k):
        chamadas.append([str(x) for x in a])
        return (1, "") if a[0] == "showvminfo" else (0, "")

    monkeypatch.setattr(vm, "_vb", falso)
    vm.criar("win.iso")
    mod = next(c for c in chamadas if c[0] == "modifyvm")
    assert "nat" in mod and "disabled" in mod  # rede NAT, sem area de transferencia
    assert not any(c[0] == "sharedfolder" for c in chamadas)
