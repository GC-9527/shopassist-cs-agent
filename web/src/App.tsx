import { useEffect, useState } from "react";
import AdminConsole from "./components/AdminConsole";
import CustomerChat from "./components/CustomerChat";
import { fetchHealth, loginDemo, setAuthToken } from "./api";
import type { DemoSession } from "./api";
import { SHELL_COPY } from "./i18n";
import type { Lang } from "./i18n";
import { useChatSession } from "./useChatSession";

// 语言与租户一一对应：zh 挂中文语料和中式订单，us 挂英文语料和美式订单。
const TENANT_BY_LANG: Record<Lang, string> = { zh: "zh", en: "us" };

// 演示账号来自后端白名单（DEMO_LOGIN_USERS）；身份由令牌携带，不由前端自报。
const ACCOUNTS = [
  { id: "u001", label: "u001 · 客户" },
  { id: "u002", label: "u002 · 客户" },
  { id: "u003", label: "u003 · 坐席" },
  { id: "u004", label: "u004 · 运营" },
  { id: "u005", label: "u005 · 客户" },
] as const;

function startsInAdmin(): boolean {
  return window.location.pathname.startsWith("/admin");
}

export default function App() {
  const [adminView] = useState(startsInAdmin);
  const [account, setAccount] = useState<string>(adminView ? "u003" : "u001");
  const [lang, setLang] = useState<Lang>("zh");
  const [session, setSession] = useState<DemoSession | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [ready, setReady] = useState<boolean | null>(null);
  const chat = useChatSession(session);
  const sys = SHELL_COPY[lang];
  const tenantId = TENANT_BY_LANG[lang];

  useEffect(() => {
    fetchHealth()
      .then((result) => setReady(result.ready))
      .catch(() => setReady(false));
  }, []);

  // 账号或语言变化都重新换取令牌：身份与租户都由令牌决定。
  useEffect(() => {
    let cancelled = false;
    setSession(null);
    setLoginError(null);
    setAuthToken(null);
    chat.reset();
    loginDemo(account, tenantId)
      .then((next) => {
        if (cancelled) return;
        setAuthToken(next.access_token);
        setSession(next);
      })
      .catch((err) => {
        if (!cancelled) setLoginError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
    // chat.reset 是稳定引用，不参与依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account, tenantId]);

  if (!adminView) {
    return (
      <div className="shell">
        <CustomerChat
          chat={chat}
          loginError={loginError}
          tenantId={session?.tenant_id ?? tenantId}
          userId={session?.user_id ?? ""}
          lang={lang}
          account={account}
          accounts={ACCOUNTS}
          onAccountChange={setAccount}
          onLangChange={setLang}
        />
      </div>
    );
  }

  const canUseAdmin =
    session?.roles.includes("agent") || session?.roles.includes("operator") || false;

  return (
    <div className="shell">
      <header className="masthead">
        <div className="wordmark">
          ShopAssist
          <span>{sys.console}</span>
        </div>
        <span className="health">
          <span className={`dot ${ready === null ? "" : ready ? "ok" : "bad"}`} />
          {ready === null ? sys.checking : ready ? sys.ready : sys.down}
        </span>
        <nav className="view-switch">
          <a href="/">{sys.support}</a>
          <a className="active" href="/admin">
            {sys.console}
          </a>
        </nav>
        <div className="context">
          <label>
            {sys.demoAccount}
            <select value={account} onChange={(event) => setAccount(event.target.value)}>
              {ACCOUNTS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          {session ? (
            <span className="badge petrol">{session.roles.join(" / ")}</span>
          ) : (
            <span className="badge brick">{loginError ? "未登录" : "登录中"}</span>
          )}
        </div>
      </header>

      {canUseAdmin && session ? (
        <AdminConsole
          chat={chat}
          tenantId={session.tenant_id}
          agentId={session.user_id}
          roles={session.roles}
        />
      ) : (
        <div className="blocked">
          <h2>需要坐席或运营身份</h2>
          <p>
            当前账号角色是 {session ? session.roles.join(" / ") : "未登录"}，不能访问运营后台。
            把右上角演示账号切换为 “u003 · 坐席” 再试。
          </p>
          {loginError ? <div className="error-line">{loginError}</div> : null}
        </div>
      )}
    </div>
  );
}
