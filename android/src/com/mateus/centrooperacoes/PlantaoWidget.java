package com.mateus.centrooperacoes;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

import org.json.JSONArray;
import org.json.JSONObject;

/** Widget "Plantão" da tela inicial. O AlertaService atualiza a cada minuto com o resumo que vem do PC
 *  (o mesmo desenho vai na notificação fixa da tela de bloqueio). Fora do plantão mostra só "sem plantão". */
public class PlantaoWidget extends AppWidgetProvider {

    @Override
    public void onUpdate(Context c, AppWidgetManager m, int[] ids) {
        AlertaService.iniciar(c);  // garante o serviço que alimenta o widget
        String salvo = c.getSharedPreferences("alertas", Context.MODE_PRIVATE).getString("painel_json", null);
        JSONObject p = null;
        try {
            if (salvo != null) p = new JSONObject(salvo);
        } catch (Exception ignorada) {
        }
        m.updateAppWidget(ids, montar(c, p, p == null ? "Aguardando o primeiro contato com o PC…" : null));
    }

    /** Atualiza todos os widgets colocados na tela (nenhum: não faz nada). */
    public static void atualizar(Context c, JSONObject painel, String rodapeExtra) {
        AppWidgetManager m = AppWidgetManager.getInstance(c);
        int[] ids = m.getAppWidgetIds(new ComponentName(c, PlantaoWidget.class));
        if (ids == null || ids.length == 0) return;
        m.updateAppWidget(ids, montar(c, painel, rodapeExtra));
    }

    /** O painel desenhado (widget e notificação da tela de bloqueio). */
    public static RemoteViews montar(Context c, JSONObject p, String rodapeExtra) {
        RemoteViews v = new RemoteViews(c.getPackageName(), R.layout.plantao_widget);
        Intent abrir = new Intent(c, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        v.setOnClickPendingIntent(R.id.pw_raiz, PendingIntent.getActivity(c, 7, abrir,
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT));
        boolean ativo = p != null && p.optBoolean("plantao");
        if (!ativo) {
            v.setTextViewText(R.id.pw_titulo, "○ SEM PLANTÃO ATIVO");
            v.setTextColor(R.id.pw_titulo, 0xFF8FA3C7);
            for (int id : new int[]{R.id.pw_crit, R.id.pw_alerta, R.id.pw_trat, R.id.pw_campo}) v.setTextViewText(id, "–");
            v.setTextViewText(R.id.pw_linhas, "O painel do plantão aparece aqui quando o plantão for iniciado no PC.");
            v.setTextViewText(R.id.pw_rodape, rodapeExtra != null ? rodapeExtra : "");
            return v;
        }
        long inicio = p.optLong("inicio_ts") * 1000;
        String ha = inicio > 0 ? " · há " + duracao(System.currentTimeMillis() - inicio) : "";
        v.setTextViewText(R.id.pw_titulo, "● PLANTÃO ATIVO" + ha + " · " + p.optString("titulo").toUpperCase());
        v.setTextColor(R.id.pw_titulo, 0xFF56CCFF);
        v.setTextViewText(R.id.pw_crit, String.valueOf(p.optInt("criticas")));
        v.setTextViewText(R.id.pw_alerta, String.valueOf(p.optInt("alertas")));
        v.setTextViewText(R.id.pw_trat, String.valueOf(p.optInt("tratativa")));
        v.setTextViewText(R.id.pw_campo, String.valueOf(p.optInt("em_campo")));
        StringBuilder linhas = new StringBuilder();
        JSONArray ls = p.optJSONArray("linhas");
        for (int i = 0; ls != null && i < ls.length(); i++) {
            if (linhas.length() > 0) linhas.append('\n');
            linhas.append(ls.optString(i));
        }
        v.setTextViewText(R.id.pw_linhas, linhas.length() > 0 ? linhas : "Nenhuma ocorrência andando agora. ✅");
        StringBuilder rod = new StringBuilder();
        JSONArray inmet = p.optJSONArray("inmet");
        if (inmet != null && inmet.length() > 0) {
            rod.append("⚠️ INMET: ");
            for (int i = 0; i < inmet.length(); i++) rod.append(i > 0 ? ", " : "").append(inmet.optString(i));
            rod.append(" · ");
        }
        rod.append(rodapeExtra != null ? rodapeExtra : "atualizado " + new java.text.SimpleDateFormat("HH:mm",
                new java.util.Locale("pt", "BR")).format(new java.util.Date(p.optLong("quando") * 1000)));
        v.setTextViewText(R.id.pw_rodape, rod);
        return v;
    }

    static String duracao(long ms) {
        long min = Math.max(0, ms / 60000), h = min / 60, d = h / 24;
        if (d > 0) return d + "d" + (h % 24) + "h";
        if (h > 0) return h + "h" + String.format("%02d", min % 60);
        return min + " min";
    }
}
