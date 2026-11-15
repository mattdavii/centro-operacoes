package com.mateus.centrooperacoes;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.widget.Toast;
import org.json.JSONObject;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/** Tela do app: o mesmo painel do PC, que busca os dados no PC pelo Tailscale e guarda os últimos para quando
 *  o PC estiver offline. O endereço do PC e a senha vêm do pareamento (QR do PC → centrooperacoes://parear),
 *  guardados só neste celular. As notificações ficam com o AlertaService. */
public class MainActivity extends Activity {
    private WebView web;

    @Override
    protected void onCreate(Bundle estado) {
        super.onCreate(estado);
        getWindow().setStatusBarColor(0xFF050A18);
        getWindow().setNavigationBarColor(0xFF03060F);

        web = new WebView(this);
        web.setBackgroundColor(0xFF03060F);
        setContentView(web);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowUniversalAccessFromFileURLs(true);  // a página local fala com o PC (http://100.x pelo Tailscale)
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);

        web.setWebChromeClient(new WebChromeClient());  // alert(), confirm() e prompt() do painel
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest req) {
                String u = req.getUrl().toString();
                if (u.startsWith("file:")) return false;
                abrirFora(u);  // relatórios e links externos vão para o navegador do celular
                return true;
            }
        });
        web.addJavascriptInterface(new Ponte(), "CentroApp");
        if (getIntent() != null && getIntent().getData() != null) parear(getIntent().getData());
        if (estado != null) web.restoreState(estado);
        else web.loadUrl("file:///android_asset/index.html");  // index.html baixa a tela mais nova do PC

        pedirPermissoes();
        AlertaService.iniciar(this);
    }

    /** Voltar: primeiro fecha o detalhe aberto ou sai do mapa; sem nada para voltar, minimiza (não fecha) o app. */
    @Override
    public void onBackPressed() {
        web.evaluateJavascript("window.voltar ? window.voltar() : false", r -> {
            if (!"true".equals(r)) moveTaskToBack(true);
        });
    }

    /** O QR do PC abriu o app: guarda o endereço e a senha e recarrega. */
    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (intent.getData() != null && parear(intent.getData())) web.loadUrl("file:///android_asset/index.html");
    }

    private boolean parear(Uri u) {
        if (!"centrooperacoes".equals(u.getScheme())) return false;
        String base = u.getQueryParameter("base"), token = u.getQueryParameter("t");
        if (base == null || token == null || !base.startsWith("http")) return false;
        salvar(this, base, token);
        Toast.makeText(this, "Conectado ao PC " + base, Toast.LENGTH_LONG).show();
        AlertaService.reiniciar(this);
        return true;
    }

    static void salvar(android.content.Context c, String base, String token) {
        c.getSharedPreferences("conexao", MODE_PRIVATE).edit().putString("base", base.replaceAll("/$", ""))
                .putString("token", token).apply();
    }

    static String[] conexao(android.content.Context c) {
        SharedPreferences p = c.getSharedPreferences("conexao", MODE_PRIVATE);
        return new String[]{p.getString("base", ""), p.getString("token", "")};
    }

    @Override
    protected void onSaveInstanceState(Bundle saida) {
        super.onSaveInstanceState(saida);
        web.saveState(saida);
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.evaluateJavascript("typeof carregar === 'function' && carregar()", null);  // atualiza ao voltar para o app
    }

    private void pedirPermissoes() {
        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }
        // sem isso o Android pode pausar o monitoramento com a tela apagada; pergunta uma vez só
        SharedPreferences p = getSharedPreferences("app", MODE_PRIVATE);
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName()) && !p.getBoolean("perguntou_bateria", false)) {
            p.edit().putBoolean("perguntou_bateria", true).apply();
            try {
                startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                        Uri.parse("package:" + getPackageName())));
            } catch (Exception ignorada) {
            }
        }
    }

    static int versaoInstalada(android.content.Context c) {
        try {
            return (int) c.getPackageManager().getPackageInfo(c.getPackageName(), 0).getLongVersionCode();
        } catch (Exception e) {
            return 0;
        }
    }

    private void abrirFora(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception ignorada) {
        }
    }

    /** Chamado pela página: window.CentroApp.abrir(url). */
    public class Ponte {
        @JavascriptInterface
        public void abrir(String url) {
            runOnUiThread(() -> abrirFora(url));
        }

        /** Endereço do PC e senha deste celular (do pareamento), para a página. */
        @JavascriptInterface
        public String config() {
            String[] c = conexao(MainActivity.this);
            try {
                return new JSONObject().put("base", c[0]).put("token", c[1]).toString();
            } catch (Exception e) {
                return "{}";
            }
        }

        /** Pareamento manual: a pessoa colou o link do QR. */
        @JavascriptInterface
        public boolean conectar(String link) {
            try {
                Uri u = Uri.parse(link.trim());
                String t = u.getQueryParameter("t");
                String base = u.getScheme() + "://" + u.getAuthority();
                if (t == null || !base.startsWith("http")) return false;
                salvar(MainActivity.this, base, t);
                runOnUiThread(() -> {
                    AlertaService.reiniciar(MainActivity.this);
                    web.loadUrl("file:///android_asset/index.html");
                });
                return true;
            } catch (Exception e) {
                return false;
            }
        }

        /** Desconectar deste PC (para parear com outro). */
        @JavascriptInterface
        public void esquecer() {
            salvar(MainActivity.this, "", "");
            runOnUiThread(() -> web.loadUrl("file:///android_asset/index.html"));
        }

        /** Painel do plantão na tela de bloqueio: {"ativo": escolhido, "permissao": pode sobrepor}. */
        @JavascriptInterface
        public String telaBloqueio() {
            boolean ativo = getSharedPreferences("app", MODE_PRIVATE).getBoolean("tela_bloqueio", true);
            return "{\"ativo\":" + ativo + ",\"permissao\":" + Settings.canDrawOverlays(MainActivity.this) + "}";
        }

        /** Liga/desliga. Ligar sem a permissão abre a tela do Android "Sobrepor a outros apps". */
        @JavascriptInterface
        public void ativarTelaBloqueio(boolean ativo) {
            getSharedPreferences("app", MODE_PRIVATE).edit().putBoolean("tela_bloqueio", ativo).apply();
            if (ativo && !Settings.canDrawOverlays(MainActivity.this)) {
                runOnUiThread(() -> {
                    try {
                        startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:" + getPackageName())));
                        Toast.makeText(MainActivity.this, "Ative \"Permitir sobreposição\" para o Centro de Operações", Toast.LENGTH_LONG).show();
                    } catch (Exception ignorada) {
                    }
                });
            }
        }

        /** Versão instalada do app, para o painel avisar quando houver uma mais nova no PC. */
        @JavascriptInterface
        public int versao() {
            return versaoInstalada(MainActivity.this);
        }
    }
}
