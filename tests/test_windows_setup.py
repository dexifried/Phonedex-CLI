"""Offline Windows-first onboarding tests; never call a carrier or install tools."""
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import json

import pytest
from rich.console import Console

from phonedex_cli import core, windows_setup as journey


def cockpit(root=None):
    output = io.StringIO()
    console = Console(file=output, force_terminal=False, color_system=None)
    cli = SimpleNamespace(console=console, banner=MagicMock(), root=lambda: root,
                          dial=MagicMock(return_value=0))
    return cli, output


def test_agentphone_trunks_uses_read_only_https_and_does_not_print_key():
    key = "secret-test-key-not-for-logging"
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):
            assert limit == 262145
            return json.dumps({"data":[{"id":"trunk", "name":"Test", "terminationSipUri":"sips:test.pstn.agentphone.ai"}]}).encode()
    class Opener:
        def open(self,request,timeout):
            assert request.get_method() == "GET"
            assert request.full_url == journey.AGENTPHONE_ENDPOINT
            assert request.get_header("Authorization") == "Bearer "+key
            assert timeout == 12
            return Response()
    with patch.object(journey,"build_opener",return_value=Opener()) as opener:
        trunks=journey.agentphone_trunks(key)
    assert trunks[0]["id"] == "trunk"
    assert isinstance(opener.call_args[0][0],journey._NoRedirect)


def test_agentphone_rejects_invalid_key_before_request():
    with patch.object(journey,"build_opener") as opener:
        with pytest.raises(ValueError):
            journey.agentphone_trunks("bad\nHeader: injected")
        opener.assert_not_called()


def test_snapshot_does_not_treat_exit_zero_as_ready(tmp_path):
    fake=SimpleNamespace(returncode=0,stdout="PhoneDex readiness: local outbound mode\n  OK  Python 3.11+\n  TODO Codex login: sign in\n")
    with patch.object(core,"core_argv",return_value=["python","setup"]), \
         patch.object(core,"safe_exec",return_value=fake):
        status=journey.setup_snapshot(tmp_path)
    assert status["local_ready"] is False
    assert any("Codex login" in item for item in status["missing"])


def test_snapshot_treats_all_required_core_checkmarks_as_ready(tmp_path):
    required=("Python 3.11+","Python packages","Codex CLI","Codex login",
              "SIP termination","Public IPv4","Caller ID","SIP credentials",
              "Dial allowlist","SRTP UDP forwarding")
    fake=SimpleNamespace(returncode=0,stdout="\n".join("  OK  "+name for name in required))
    with patch.object(core,"core_argv",return_value=["python","setup"]), \
         patch.object(core,"safe_exec",return_value=fake):
        assert journey.setup_snapshot(tmp_path)["local_ready"]


def test_media_confirmation_only_on_explicit_yes(tmp_path):
    env=tmp_path/".env"
    env.write_text("PHONEDEX_MEDIA_PORT=41002\nPHONEDEX_MEDIA_PORT_FORWARDED=0\n")
    cli,_=cockpit(tmp_path)
    with patch.object(journey,"local_ipv4",return_value="192.168.0.21"), \
         patch.object(journey.Confirm,"ask",return_value=False):
        journey._network_guide(tmp_path,cli)
    assert core.parse_env(env)["PHONEDEX_MEDIA_PORT_FORWARDED"] == "0"
    with patch.object(journey,"local_ipv4",return_value="192.168.0.21"), \
         patch.object(journey.Confirm,"ask",return_value=True):
        journey._network_guide(tmp_path,cli)
    assert core.parse_env(env)["PHONEDEX_MEDIA_PORT_FORWARDED"] == "1"


def test_windows_wizard_refuses_non_windows_without_work():
    cli,_=cockpit()
    with patch.object(journey,"IS_WINDOWS",False), \
         patch.object(journey,"_choose_checkout") as choose:
        assert journey.run(cli) is False
        choose.assert_not_called()


def test_existing_configuration_is_never_overwritten(tmp_path):
    path=tmp_path/".env"
    path.write_text("PHONEDEX_SIP_PASSWORD=keep-this-secret\n",encoding="utf-8")
    cli,_=cockpit(tmp_path)
    with patch.object(journey.Prompt,"ask") as ask:
        assert journey._provider_configuration(tmp_path,cli)
    ask.assert_not_called()
    assert "keep-this-secret" in path.read_text()


def test_core_config_prompt_creates_new_env_once(tmp_path):
    saved=[]
    def v(value):
        if not value:raise ValueError("missing")
        return value
    onboarding=SimpleNamespace(sip_target=v,e164=v,public_ipv4=v,checked_field=v,
        approved_recipients=v,save_env=lambda root, values:
        (saved.append(dict(values)), (root/".env").write_text("PHONEDEX_SIP_PASSWORD="+values["PHONEDEX_SIP_PASSWORD"]+"\n")))
    cli,out=cockpit(tmp_path)
    answers=iter(["agentphone","sips:example.pstn.agentphone.ai","+14165550101",
                  "203.0.113.4","alice","+14165550102"])
    with patch.object(journey,"_load_onboarding",return_value=onboarding), \
         patch.object(journey,"_agentphone_preset",return_value={}), \
         patch.object(journey.Prompt,"ask",side_effect=lambda *a,**kw: next(answers)), \
         patch.object(journey.Confirm,"ask",return_value=True), \
         patch.object(journey.getpass,"getpass",return_value="private-sip-password"):
        assert journey._provider_configuration(tmp_path,cli)
    assert len(saved)==1
    assert saved[0]["PHONEDEX_TRANSCRIPT_MODE"]=="off"
    assert saved[0]["PHONEDEX_MEDIA_PORT_FORWARDED"]=="0"
    assert "private-sip-password" in (tmp_path/".env").read_text()
    assert "private-sip-password" not in out.getvalue()
    assert not (tmp_path/"agentphone_api_key.txt").exists()


def test_agentphone_trunk_picker_does_not_show_credentials():
    cli,out=cockpit()
    response=[{"name":"My trunk","transport":"tls","mediaEncryption":"srtp",
               "terminationSipUri":"sips:foo.pstn.agentphone.ai",
               "credentials":[{"username":"sip-user","password":"top-secret"}]}]
    with patch.object(journey.Confirm,"ask",return_value=True), \
         patch.object(journey.getpass,"getpass",return_value="hidden-agentphone-key"), \
         patch.object(journey,"agentphone_trunks",return_value=response), \
         patch.object(journey.Prompt,"ask",return_value="1"):
        selected=journey._agentphone_preset(cli.console)
    assert selected["password"] == "top-secret"
    assert "top-secret" not in out.getvalue()
    assert "hidden-agentphone-key" not in out.getvalue()


def test_windows_wizard_no_real_call_without_explicit_confirmation(tmp_path):
    cli,_=cockpit(tmp_path)
    (tmp_path/".env").write_text("PHONEDEX_ALLOWED_RECIPIENTS=+14165550102\n")
    with patch.object(journey,"IS_WINDOWS",True), \
         patch.object(journey,"_choose_checkout",return_value=tmp_path), \
         patch.object(journey,"_bootstrap",return_value=True), \
         patch.object(journey,"_ensure_codex",return_value=True), \
         patch.object(journey,"_codex_login",return_value=True), \
         patch.object(journey,"_provider_configuration",return_value=True), \
         patch.object(journey,"_network_guide"), \
         patch.object(journey,"setup_snapshot",return_value={"local_ready":True,"missing":[],"details":"all ready"}), \
         patch.object(journey.Confirm,"ask",side_effect=[True,False]), \
         patch.object(journey.Prompt,"ask",return_value="+14165550102"):
        assert journey.run(cli) is True
    cli.dial.assert_called_once_with("+14165550102",duration=30)
    assert not cli.dial.call_args.kwargs.get("place_call",False)


def test_no_node_install_without_permission():
    cli,_=cockpit()
    with patch.object(journey,"_tool",return_value="winget.exe"), \
         patch.object(journey.Confirm,"ask",return_value=False), \
         patch.object(journey.subprocess,"call") as call:
        assert journey._install_tool("node",cli.console) is False
        call.assert_not_called()


def test_trunk_creation_requires_separate_confirmation():
    cli,_=cockpit()
    with patch.object(journey.Confirm,"ask",side_effect=[True,False]), \
         patch.object(journey.getpass,"getpass",return_value="ephemeral-key"), \
         patch.object(journey,"agentphone_trunks",return_value=[]), \
         patch.object(journey,"create_agentphone_trunk") as create:
        assert journey._agentphone_preset(cli.console)=={}
        create.assert_not_called()


def test_trunk_creation_only_once_after_explicit_permission():
    cli,_=cockpit()
    created={"name":"New trunk","transport":"tls","terminationSipUri":"sips:test.pstn.agentphone.ai",
             "credentials":[{"username":"trunk-username","password":"trunk-password"}]}
    with patch.object(journey.Confirm,"ask",side_effect=[True,True]), \
         patch.object(journey.getpass,"getpass",return_value="ephemeral-key"), \
         patch.object(journey,"agentphone_trunks",return_value=[]), \
         patch.object(journey,"create_agentphone_trunk",return_value=created) as create:
        selected=journey._agentphone_preset(cli.console)
    create.assert_called_once_with("ephemeral-key")
    assert selected["uri"]=="sips:test.pstn.agentphone.ai"
    assert selected["username"]=="trunk-username"


def test_provider_creation_uses_post_with_no_redirect():
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,count):return b'{"id":"new-trunk","terminationSipUri":"sips:new.example"}'
    class Opener:
        def open(self,request,timeout):
            assert request.get_method()=="POST"
            assert request.data==b"{}"
            assert request.full_url==journey.AGENTPHONE_ENDPOINT
            assert request.get_header("Authorization")=="Bearer ephemeral-key"
            assert timeout==20
            return Response()
    with patch.object(journey,"build_opener",return_value=Opener()):
        result=journey.create_agentphone_trunk("ephemeral-key")
    assert result["id"]=="new-trunk"


def test_missing_venv_never_runs_bootstrap(tmp_path):
    cli,_=cockpit(tmp_path)
    with patch.object(journey.importlib.util,"find_spec",return_value=None), \
         patch.object(journey,"_install_tool",return_value=False), \
         patch.object(journey.subprocess,"call") as call:
        assert journey._bootstrap(tmp_path,cli) is False
        call.assert_not_called()
