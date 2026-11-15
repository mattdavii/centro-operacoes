package com.mateus.centrooperacoes;

import android.app.Activity;
import android.app.KeyguardManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONObject;

/** Painel do plantão por cima da tela de bloqueio (como o despertador faz). O AlertaService abre esta tela
 *  quando a tela do celular acende com o plantão ativo. Some ao desbloquear ou em "Fechar".
 *  Não depende das configurações de notificação da tela de bloqueio; precisa só de "Sobrepor a outros apps". */
public class PlantaoBloqueioActivity extends Activity {
    private FrameLayout caixa;
    private final Handler relogio = new Handler(Looper.getMainLooper());
    private final BroadcastReceiver desbloqueou = new BroadcastReceiver() {
        @Override
        public void onReceive(Context c, Intent i) {
            finish();  // a pessoa desbloqueou: a tela do plantão sai do caminho
        }
    };

    @Override
    protected void onCreate(Bundle estado) {
        super.onCreate(estado);
        setShowWhenLocked(true);
        setTurnScreenOn(false);
        getWindow().setStatusBarColor(0xFF03060F);
        getWindow().setNavigationBarColor(0xFF03060F);

        float dp = getResources().getDisplayMetrics().density;
        LinearLayout raiz = new LinearLayout(this);
        raiz.setOrientation(LinearLayout.VERTICAL);
        raiz.setGravity(Gravity.CENTER_HORIZONTAL);
        raiz.setBackgroundColor(0xF203060F);
        raiz.setPadding((int) (16 * dp), (int) (48 * dp), (int) (16 * dp), (int) (24 * dp));

        TextView topo = new TextView(this);
        topo.setText("CENTRO DE OPERAÇÕES · PLANTÃO");
        topo.setTextColor(0xFF8FA3C7);
        topo.setTextSize(11);
        topo.setLetterSpacing(0.12f);
        topo.setPadding(0, 0, 0, (int) (10 * dp));
        raiz.addView(topo);

        caixa = new FrameLayout(this);
        raiz.addView(caixa, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        LinearLayout botoes = new LinearLayout(this);
        botoes.setOrientation(LinearLayout.HORIZONTAL);
        botoes.setPadding(0, (int) (14 * dp), 0, 0);
        Button abrir = botao("ABRIR PAINEL", 0xFF0F3550, 0xFF9FDCFF);
        abrir.setOnClickListener(v -> abrirPainel());
        Button fechar = botao("FECHAR", 0xFF14203D, 0xFFDBE4FF);
        fechar.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        lp.setMarginEnd((int) (8 * dp));
        botoes.addView(abrir, lp);
        botoes.addView(fechar, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        raiz.addView(botoes, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));

        TextView dica = new TextView(this);
        dica.setText("Some sozinho quando você desbloqueia. Desligar: no app, botão 🔒 Tela de bloqueio.");
        dica.setTextColor(0xFF5B6B8F);
        dica.setTextSize(11);
        dica.setGravity(Gravity.CENTER);
        dica.setPadding(0, (int) (16 * dp), 0, 0);
        raiz.addView(dica);

        setContentView(raiz);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(desbloqueou, new IntentFilter(Intent.ACTION_USER_PRESENT), RECEIVER_EXPORTED);
        else registerReceiver(desbloqueou, new IntentFilter(Intent.ACTION_USER_PRESENT));
    }

    private Button botao(String texto, int fundo, int cor) {
        Button b = new Button(this);
        b.setText(texto);
        b.setTextColor(cor);
        b.setBackgroundColor(fundo);
        b.setAllCaps(false);
        return b;
    }

    @Override
    protected void onResume() {
        super.onResume();
        desenhar();
    }

    @Override
    protected void onPause() {
        relogio.removeCallbacksAndMessages(null);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        try {
            unregisterReceiver(desbloqueou);
        } catch (Exception ignorada) {
        }
        super.onDestroy();
    }

    /** Redesenha com o último resumo que o AlertaService guardou (a cada 30 s enquanto aberta). */
    private void desenhar() {
        JSONObject p = null;
        try {
            String salvo = getSharedPreferences("alertas", MODE_PRIVATE).getString("painel_json", null);
            if (salvo != null) p = new JSONObject(salvo);
        } catch (Exception ignorada) {
        }
        if (p == null || !p.optBoolean("plantao")) {
            finish();  // o plantão acabou
            return;
        }
        caixa.removeAllViews();
        View v = PlantaoWidget.montar(this, p, null).apply(this, caixa);
        v.setOnClickListener(x -> abrirPainel());
        caixa.addView(v);
        relogio.postDelayed(this::desenhar, 30_000);
    }

    private void abrirPainel() {
        KeyguardManager km = getSystemService(KeyguardManager.class);
        Intent app = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        if (km != null && km.isKeyguardLocked()) {
            km.requestDismissKeyguard(this, new KeyguardManager.KeyguardDismissCallback() {
                @Override
                public void onDismissSucceeded() {
                    startActivity(app);
                    finish();
                }
            });
        } else {
            startActivity(app);
            finish();
        }
    }

    /** O serviço chama ao acender a tela: abre só se tudo estiver certo. */
    public static boolean podeAbrir(Context c) {
        if (!c.getSharedPreferences("app", MODE_PRIVATE).getBoolean("tela_bloqueio", true)) return false;
        if (!android.provider.Settings.canDrawOverlays(c)) return false;
        KeyguardManager km = c.getSystemService(KeyguardManager.class);
        if (km == null || !km.isKeyguardLocked()) return false;
        try {
            String salvo = c.getSharedPreferences("alertas", MODE_PRIVATE).getString("painel_json", null);
            return salvo != null && new JSONObject(salvo).optBoolean("plantao");
        } catch (Exception e) {
            return false;
        }
    }
}
