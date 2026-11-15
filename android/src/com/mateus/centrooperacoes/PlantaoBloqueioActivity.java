package com.mateus.centrooperacoes;

import android.app.Activity;
import android.app.KeyguardManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextClock;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

/** Painel do plantão por cima da tela de bloqueio (como o despertador faz). O AlertaService abre esta tela
 *  quando a tela do celular acende com o plantão ativo. Some ao desbloquear ou em "Fechar".
 *  Não depende das configurações de notificação da tela de bloqueio; precisa só de "Sobrepor a outros apps".
 *  Mostra: relógio, contadores, cada ocorrência andando (status, tempo, o que houve, tempo na usina),
 *  as em tratativa, técnicos em campo, manutenções e clima (INMET). */
public class PlantaoBloqueioActivity extends Activity {
    private static final int FUNDO = 0xFF03060F, CARTAO = 0xFF0B1226, BORDA = 0xFF1E2C52, TEXTO = 0xFFE6EDFF,
            FRACO = 0xFF8FA3C7, APAGADO = 0xFF5B6B8F, CIANO = 0xFF56CCFF, VERMELHO = 0xFFFF4D5E, AMARELO = 0xFFFBBF24,
            OURO = 0xFFFDE68A, ROXO = 0xFFB49BFF, VERDE = 0xFF3EE08A, LARANJA = 0xFFFDBA74;
    private LinearLayout conteudo;
    private float dp;
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
        getWindow().setStatusBarColor(FUNDO);
        getWindow().setNavigationBarColor(FUNDO);
        dp = getResources().getDisplayMetrics().density;

        LinearLayout raiz = new LinearLayout(this);
        raiz.setOrientation(LinearLayout.VERTICAL);
        raiz.setBackgroundColor(FUNDO);

        ScrollView rolagem = new ScrollView(this);
        rolagem.setFillViewport(true);
        conteudo = new LinearLayout(this);
        conteudo.setOrientation(LinearLayout.VERTICAL);
        conteudo.setPadding(px(16), px(28), px(16), px(12));
        rolagem.addView(conteudo);
        raiz.addView(rolagem, new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1));

        LinearLayout botoes = new LinearLayout(this);
        botoes.setOrientation(LinearLayout.HORIZONTAL);
        botoes.setPadding(px(16), px(8), px(16), px(16));
        Button abrir = botao("ABRIR PAINEL", 0xFF0F3550, 0xFF9FDCFF);
        abrir.setOnClickListener(v -> abrirPainel());
        Button fechar = botao("FECHAR", 0xFF14203D, TEXTO);
        fechar.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, px(48), 1);
        lp.setMarginEnd(px(8));
        botoes.addView(abrir, lp);
        botoes.addView(fechar, new LinearLayout.LayoutParams(0, px(48), 1));
        raiz.addView(botoes);

        setContentView(raiz);
        if (Build.VERSION.SDK_INT >= 33) registerReceiver(desbloqueou, new IntentFilter(Intent.ACTION_USER_PRESENT), RECEIVER_EXPORTED);
        else registerReceiver(desbloqueou, new IntentFilter(Intent.ACTION_USER_PRESENT));
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

    // ---------------------------------------------------------------------------------------------

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
        conteudo.removeAllViews();
        long agora = System.currentTimeMillis();

        // relógio e data (a tela cobre o relógio do bloqueio)
        TextClock hora = new TextClock(this);
        hora.setFormat24Hour("HH:mm");
        hora.setFormat12Hour("HH:mm");
        hora.setTextSize(58);
        hora.setTextColor(TEXTO);
        hora.setTypeface(Typeface.create("sans-serif-light", Typeface.NORMAL));
        hora.setGravity(Gravity.CENTER);
        conteudo.addView(hora, cheio());
        TextClock data = new TextClock(this);
        data.setFormat24Hour("EEEE, d 'de' MMMM");
        data.setFormat12Hour("EEEE, d 'de' MMMM");
        data.setTextSize(14);
        data.setTextColor(FRACO);
        data.setGravity(Gravity.CENTER);
        conteudo.addView(data, cheio());

        // plantão
        long inicio = p.optLong("inicio_ts") * 1000;
        TextView pl = texto("● PLANTÃO ATIVO" + (inicio > 0 ? " · há " + PlantaoWidget.duracao(agora - inicio) : ""), 12, CIANO, true);
        pl.setGravity(Gravity.CENTER);
        pl.setLetterSpacing(0.08f);
        pl.setPadding(0, px(14), 0, 0);
        conteudo.addView(pl, cheio());
        StringBuilder sub = new StringBuilder(p.optString("titulo"));
        JSONArray eq = p.optJSONArray("equipe");
        if (eq != null && eq.length() > 0) {
            sub.append(" · ");
            for (int i = 0; i < eq.length(); i++) sub.append(i > 0 ? ", " : "").append(eq.optString(i));
        }
        TextView st = texto(sub.toString(), 12, FRACO, false);
        st.setGravity(Gravity.CENTER);
        conteudo.addView(st, cheio());
        boolean wa = p.optBoolean("whatsapp", true);
        TextView con = texto((wa ? "● " : "⚠ ") + "Atualizado " + hm(p.optLong("quando") * 1000)
                + (wa ? " · WhatsApp do PC conectado" : " · WhatsApp do PC DESCONECTADO"), 11, wa ? VERDE : VERMELHO, false);
        con.setGravity(Gravity.CENTER);
        con.setPadding(0, px(2), 0, px(12));
        conteudo.addView(con, cheio());

        // contadores
        LinearLayout cont = new LinearLayout(this);
        cont.setOrientation(LinearLayout.HORIZONTAL);
        cont.addView(contador(p.optInt("criticas"), "CRÍTICAS", VERMELHO), peso(true));
        cont.addView(contador(p.optInt("alertas"), "ALERTAS", AMARELO), peso(true));
        cont.addView(contador(p.optInt("tratativa"), "TRATATIVA", OURO), peso(true));
        cont.addView(contador(p.optInt("em_campo"), "EM CAMPO", ROXO), peso(true));
        cont.addView(contador(p.optInt("resolvidas_24h"), "RESOLV. 24H", VERDE), peso(false));
        conteudo.addView(cont, cheio());

        // ocorrências andando
        JSONArray ocs = p.optJSONArray("ocorrencias");
        secao("🚨 ANDANDO AGORA", ocs == null ? 0 : ocs.length());
        if (ocs == null || ocs.length() == 0) vazio("Nenhuma ocorrência andando agora. ✅");
        for (int i = 0; ocs != null && i < ocs.length(); i++) cartaoOcorrencia(ocs.optJSONObject(i), agora);

        // em tratativa
        JSONArray tr = p.optJSONArray("tratativa_lista");
        if (tr != null && tr.length() > 0) {
            secao("⏳ EM TRATATIVA", p.optInt("tratativa"));
            for (int i = 0; i < tr.length(); i++) {
                JSONObject o = tr.optJSONObject(i);
                LinearLayout c = cartao("critico".equals(o.optString("sev")) ? VERMELHO : AMARELO);
                linhaTitulo(c, o.optString("usina"), "há " + PlantaoWidget.duracao(agora - o.optLong("desde") * 1000));
                if (!o.optString("motivo").isEmpty()) c.addView(texto(o.optString("motivo"), 12, OURO, false, 2), cheio());
            }
        }

        // técnicos em campo
        JSONArray campo = p.optJSONArray("campo");
        secao("👷 EM CAMPO", campo == null ? 0 : campo.length());
        if (campo == null || campo.length() == 0) vazio("Nenhum técnico registrou entrada.");
        for (int i = 0; campo != null && i < campo.length(); i++) {
            JSONObject x = campo.optJSONObject(i);
            long desde = x.optLong("desde") * 1000;
            lista(x.optString("tecnico"), x.optString("usina") + " · desde " + hm(desde) + " (" + PlantaoWidget.duracao(agora - desde) + ")", ROXO);
        }

        // manutenções
        JSONArray man = p.optJSONArray("manutencoes");
        if (man != null && man.length() > 0) {
            secao("🔧 MANUTENÇÕES EM ANDAMENTO", man.length());
            for (int i = 0; i < man.length(); i++) {
                JSONObject a = man.optJSONObject(i);
                lista(a.optString("usina"), a.optString("descricao") + " · desde " + hm(a.optLong("desde") * 1000), 0xFF3987E5);
            }
        }

        // clima
        JSONObject cl = p.optJSONObject("clima");
        if (cl != null) {
            JSONArray av = cl.optJSONArray("avisos");
            secao("⛈️ CLIMA NAS USINAS", -1);
            LinearLayout c = cartao(LARANJA);
            for (int i = 0; av != null && i < av.length(); i++) {
                JSONObject a = av.optJSONObject(i);
                String fim = a.optString("fim");
                c.addView(texto("⚠️ INMET: " + a.optString("descricao") + " (" + a.optString("severidade") + ")"
                        + (fim.length() >= 16 ? " até " + fim.substring(11, 16) : "") + " · " + a.optInt("usinas") + " usinas", 13, OURO, true), cheio());
            }
            if (av == null || av.length() == 0) c.addView(texto("Nenhum aviso do INMET sobre as usinas.", 13, FRACO, false), cheio());
            c.addView(texto("🌧️ Chuva ou vento agora em " + cl.optInt("chuva_agora") + " locais · ⛈️ temporal previsto (6 h) em "
                    + cl.optInt("temporal_6h"), 12, TEXTO, false), cheio());
        }

        TextView dica = texto("Some sozinho quando você desbloqueia. Desligar: no app, botão 🔒 Tela de bloqueio.", 11, APAGADO, false);
        dica.setGravity(Gravity.CENTER);
        dica.setPadding(0, px(16), 0, 0);
        conteudo.addView(dica, cheio());

        relogio.postDelayed(this::desenhar, 30_000);
    }

    private void cartaoOcorrencia(JSONObject o, long agora) {
        if (o == null) return;
        boolean critica = "critico".equals(o.optString("sev"));
        LinearLayout c = cartao(critica ? VERMELHO : AMARELO);
        linhaTitulo(c, o.optString("usina"), "há " + PlantaoWidget.duracao(agora - o.optLong("desde") * 1000));
        LinearLayout etiquetas = new LinearLayout(this);
        etiquetas.setOrientation(LinearLayout.HORIZONTAL);
        etiquetas.setPadding(0, px(3), 0, px(3));
        etiquetas.addView(etiqueta(critica ? "CRÍTICA" : "ALERTA", critica ? 0xFF4A1520 : 0xFF3D3108, critica ? 0xFFFFC9D0 : OURO));
        String[] st = rotuloStatus(o.optString("status"));
        etiquetas.addView(etiqueta(st[0], Integer.parseInt(st[1].substring(2), 16) | 0xFF000000, Integer.parseInt(st[2].substring(2), 16) | 0xFF000000));
        c.addView(etiquetas);
        c.addView(texto(o.optString("texto"), 13, 0xFFC9D4F0, false, 3), cheio());
        String motivo = o.optString("motivo");
        String s = o.optString("status");
        if (!motivo.isEmpty() && ("em_atendimento".equals(s) || "a_caminho".equals(s)))
            c.addView(texto("↳ " + motivo, 12, ROXO, false, 2), cheio());
        if (!o.optString("agora").isEmpty() && !"null".equals(o.optString("agora")))
            c.addView(texto("Agora: " + o.optString("agora"), 12, 0xFF9BD6FF, false), cheio());
        JSONArray pv = o.optJSONArray("previsao");
        if (pv != null && pv.length() == 2)
            c.addView(texto("Previsão " + hm(pv.optLong(1) * 1000) + ": " + pv.optString(0), 12, LARANJA, false), cheio());
        JSONArray inmet = o.optJSONArray("inmet");
        if (inmet != null && inmet.length() > 0) {
            StringBuilder b = new StringBuilder("⚠️ INMET: ");
            for (int i = 0; i < inmet.length(); i++) b.append(i > 0 ? ", " : "").append(inmet.optString(i));
            c.addView(texto(b.toString(), 12, OURO, false), cheio());
        }
        long ultima = o.optLong("ultima") * 1000;
        if (ultima > 0) c.addView(texto("último aviso " + hm(ultima), 10, APAGADO, false), cheio());
    }

    private static String[] rotuloStatus(String s) {
        switch (s) {
            case "cog_validando": return new String[]{"🖥️ COG VALIDANDO", "0x10343A", "0xA5F3FC"};
            case "a_caminho": return new String[]{"🚗 TÉCNICO A CAMINHO", "0x0F3550", "0x9FDCFF"};
            case "em_atendimento": return new String[]{"👷 EM ATENDIMENTO", "0x2A2158", "0xD6C8FF"};
            case "em_tratativa": return new String[]{"⏳ EM TRATATIVA", "0x3D3108", "0xFDE68A"};
            default: return new String[]{"EM ABERTO", "0x3A2230", "0xFFC9D0"};
        }
    }

    // ---------- peças de desenho ----------

    private int px(float v) {
        return (int) (v * dp);
    }

    private LinearLayout.LayoutParams cheio() {
        return new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
    }

    private LinearLayout.LayoutParams peso(boolean margem) {
        LinearLayout.LayoutParams l = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1);
        if (margem) l.setMarginEnd(px(5));
        return l;
    }

    private GradientDrawable fundo(int cor, int borda, float raio) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(cor);
        g.setCornerRadius(raio * dp);
        if (borda != 0) g.setStroke(px(1), borda);
        return g;
    }

    private TextView texto(String t, float tam, int cor, boolean negrito) {
        return texto(t, tam, cor, negrito, 0);
    }

    private TextView texto(String t, float tam, int cor, boolean negrito, int maxLinhas) {
        TextView v = new TextView(this);
        v.setText(t);
        v.setTextSize(tam);
        v.setTextColor(cor);
        if (negrito) v.setTypeface(Typeface.DEFAULT_BOLD);
        if (maxLinhas > 0) {
            v.setMaxLines(maxLinhas);
            v.setEllipsize(TextUtils.TruncateAt.END);
        }
        v.setLineSpacing(px(1), 1f);
        return v;
    }

    private View contador(int n, String rotulo, int cor) {
        LinearLayout b = new LinearLayout(this);
        b.setOrientation(LinearLayout.VERTICAL);
        b.setGravity(Gravity.CENTER);
        b.setBackground(fundo(0xFF14203D, 0, 10));
        b.setPadding(0, px(7), 0, px(7));
        TextView num = texto(String.valueOf(n), 22, cor, true);
        num.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        num.setGravity(Gravity.CENTER);
        b.addView(num);
        TextView r = texto(rotulo, 8, FRACO, true, 1);
        r.setGravity(Gravity.CENTER);
        b.addView(r);
        return b;
    }

    private void secao(String titulo, int qtd) {
        TextView t = texto(titulo + (qtd >= 0 ? "  ·  " + qtd : ""), 11, FRACO, true);
        t.setLetterSpacing(0.1f);
        t.setPadding(px(2), px(18), 0, px(6));
        conteudo.addView(t, cheio());
    }

    private void vazio(String t) {
        TextView v = texto(t, 13, APAGADO, false);
        v.setPadding(px(2), 0, 0, px(2));
        conteudo.addView(v, cheio());
    }

    /** Cartão com uma barra de cor à esquerda; devolve a coluna onde vai o conteúdo. */
    private LinearLayout cartao(int corBarra) {
        LinearLayout c = new LinearLayout(this);
        c.setOrientation(LinearLayout.HORIZONTAL);
        c.setBackground(fundo(CARTAO, BORDA, 10));
        View barra = new View(this);
        barra.setBackground(fundo(corBarra, 0, 2));
        LinearLayout.LayoutParams lb = new LinearLayout.LayoutParams(px(4), LinearLayout.LayoutParams.MATCH_PARENT);
        lb.setMargins(px(6), px(8), 0, px(8));
        c.addView(barra, lb);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setPadding(px(10), px(9), px(12), px(9));
        c.addView(col, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        c.setOnClickListener(v -> abrirPainel());
        LinearLayout.LayoutParams l = cheio();
        l.setMargins(0, 0, 0, px(7));
        conteudo.addView(c, l);
        return col;
    }

    private void linhaTitulo(LinearLayout c, String titulo, String direita) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.HORIZONTAL);
        l.setGravity(Gravity.CENTER_VERTICAL);
        l.addView(texto(titulo, 15, TEXTO, true, 1), new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1));
        TextView d = texto(direita, 12, FRACO, false);
        d.setTypeface(Typeface.MONOSPACE);
        l.addView(d);
        c.addView(l, cheio());
    }

    private TextView etiqueta(String t, int fundo, int cor) {
        TextView v = texto(t, 10, cor, true);
        v.setBackground(fundo(fundo, 0, 4));
        v.setPadding(px(6), px(2), px(6), px(2));
        LinearLayout.LayoutParams l = new LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        l.setMarginEnd(px(6));
        v.setLayoutParams(l);
        return v;
    }

    private void lista(String titulo, String sub, int cor) {
        LinearLayout c = cartao(cor);
        c.addView(texto(titulo, 14, TEXTO, true, 1), cheio());
        c.addView(texto(sub, 12, FRACO, false, 2), cheio());
    }

    private Button botao(String t, int fundo, int cor) {
        Button b = new Button(this);
        b.setText(t);
        b.setTextColor(cor);
        b.setBackground(fundo(fundo, 0, 10));
        b.setAllCaps(false);
        b.setTypeface(Typeface.DEFAULT_BOLD);
        return b;
    }

    private static String hm(long ms) {
        return new SimpleDateFormat("HH:mm", new Locale("pt", "BR")).format(new Date(ms));
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
