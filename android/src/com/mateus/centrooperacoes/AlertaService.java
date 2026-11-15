package com.mateus.centrooperacoes;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import android.os.IBinder;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/** Fica rodando em segundo plano: consulta o PC (pelo Tailscale) a cada minuto e avisa no celular quando
 *  aparece ocorrência crítica ou alguém te marca. Durante o plantão, crítica sem "ciente" volta a tocar a cada 5 min. */
public class AlertaService extends Service {
    private static final String CANAL_MONITOR = "monitor";
    private static final String CANAL_CRITICO = "critico_v2";  // v2: toque "alarme industrial" do próprio app
    private static final String CANAL_AVISO = "avisos";
    private static final String CANAL_SILENCIO = "silencio";  // horário de silêncio: aparece, mas sem som nem vibração
    private static final String CANAL_PLANTAO = "plantao_tela";  // painel do plantão na tela de bloqueio (sem som)
    private static final int ID_PLANTAO = 50;
    private int silencioInicio = 20, silencioFim = 7;
    private static final int ID_MONITOR = 1;
    private static final long REFORCO_MS = 5 * 60 * 1000L;

    private ScheduledExecutorService agenda;
    private String base, token;
    private SharedPreferences prefs;
    private long ultimoContato = 0, ultimoReforco = 0, waForaDesde = 0;
    private boolean avisouPcFora = false, avisouWa = false, plantaoAtivo = false;
    private static final long FORA_MS = 10 * 60 * 1000L;  // sem contato por mais que isso vira alarme
    private final long inicioServico = System.currentTimeMillis();

    public static void iniciar(Context c) {
        Intent i = new Intent(c, AlertaService.class);
        try {
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i);
            else c.startService(i);
        } catch (Exception ignorada) {
        }
    }

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences("alertas", MODE_PRIVATE);
        String[] c = MainActivity.conexao(this);  // do pareamento com o PC (QR)
        base = c[0];
        token = c[1];
        criarCanais();
        Notification n = notifMonitor("Conectando ao PC…", null);
        if (Build.VERSION.SDK_INT >= 34) startForeground(ID_MONITOR, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else startForeground(ID_MONITOR, n);
        agenda = Executors.newSingleThreadScheduledExecutor();
        agenda.scheduleWithFixedDelay(this::verificar, 0, 60, TimeUnit.SECONDS);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        if (agenda != null) agenda.shutdownNow();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    // ---------------------------------------------------------------------------------------------

    /** Pareou com um PC novo: reinicia para ler o endereço e começar do zero. */
    public static void reiniciar(Context c) {
        c.getSharedPreferences("alertas", MODE_PRIVATE).edit().clear().apply();
        c.stopService(new Intent(c, AlertaService.class));
        iniciar(c);
    }

    private void verificar() {
        if (base.isEmpty()) {
            atualizarMonitor("Abra o app e conecte ao seu PC (QR em 📱 Conectar celular)", null);
            return;
        }
        try {
            JSONObject d = new JSONObject(get(base + "/api/alertas"));
            ultimoContato = System.currentTimeMillis();
            NotificationManager nmv = getSystemService(NotificationManager.class);
            if (avisouPcFora) {
                avisouPcFora = false;
                nmv.cancel(997);
                notificar(nmv, 996, CANAL_AVISO, "✅ Contato com o PC restabelecido", "O monitoramento voltou a funcionar.");
            }
            if (!d.optBoolean("pronto")) {
                atualizarMonitor("PC sincronizando com o WhatsApp…", null);
                return;
            }
            processar(d);
        } catch (Exception e) {
            String quando = ultimoContato > 0 ? " · último contato " + hora(ultimoContato) : "";
            atualizarMonitor("PC offline ou fora do Tailscale" + quando, null);
            try {
                String salvo = prefs.getString("painel_json", null);
                if (salvo != null) desenharPainel(new JSONObject(salvo), "⚠️ sem contato com o PC" + quando);
            } catch (Exception ignorada) {
            }
            // 10 min sem falar com o PC: avisa uma vez (alarme no plantão, aviso fora dele)
            long agora = System.currentTimeMillis();
            long desde = ultimoContato > 0 ? ultimoContato : inicioServico;  // nunca falou com o PC: conta desde que o app abriu
            if (agora - desde >= FORA_MS && !avisouPcFora) {
                avisouPcFora = true;
                notificar(getSystemService(NotificationManager.class), 997, plantaoAtivo ? CANAL_CRITICO : CANAL_AVISO,
                        "⚠️ Sem contato com o PC há " + ((agora - desde) / 60000) + " min",
                        "O monitoramento está parado. Verifique se o PC está ligado e no Tailscale (ou se o celular está sem internet).");
            }
        }
    }

    private void processar(JSONObject d) throws Exception {
        JSONObject sil = d.optJSONObject("silencio");
        if (sil != null) {
            silencioInicio = sil.optInt("inicio", 20);
            silencioFim = sil.optInt("fim", 7);
        }
        boolean plantao = d.optBoolean("plantao");
        plantaoAtivo = plantao;
        // WhatsApp do PC desconectado por 10 min: o painel fica cego, avisa
        long agoraWa = System.currentTimeMillis();
        if (!"open".equals(d.optString("whatsapp"))) {
            if (waForaDesde == 0) waForaDesde = agoraWa;
            if (agoraWa - waForaDesde >= FORA_MS && !avisouWa) {
                avisouWa = true;
                notificar(getSystemService(NotificationManager.class), 995, plantao ? CANAL_CRITICO : CANAL_AVISO,
                        "⚠️ WhatsApp do PC desconectado", "O wa-app está sem conexão há " + ((agoraWa - waForaDesde) / 60000)
                                + " min: novas ocorrências não estão chegando. Abra a janela do wa-app no PC.");
            }
        } else {
            if (avisouWa) {
                getSystemService(NotificationManager.class).cancel(995);
                notificar(getSystemService(NotificationManager.class), 994, CANAL_AVISO, "✅ WhatsApp do PC reconectado", "As mensagens voltaram a chegar.");
            }
            waForaDesde = 0;
            avisouWa = false;
        }
        boolean primeira = !prefs.getBoolean("iniciado", false);  // na primeira vez só memoriza, sem tocar
        Set<String> vistos = new HashSet<>(prefs.getStringSet("vistos", new HashSet<>()));
        Set<String> atuais = new HashSet<>();
        NotificationManager nm = getSystemService(NotificationManager.class);

        JSONArray ocs = d.optJSONArray("ocorrencias");
        int criticas = 0, alertas = 0, semCiente = 0;
        JSONObject primeiraSemCiente = null;
        for (int i = 0; ocs != null && i < ocs.length(); i++) {
            JSONObject o = ocs.getJSONObject(i);
            boolean critica = "critico".equals(o.optString("sev"));
            if (critica) criticas++; else alertas++;
            if (critica && !o.optBoolean("ciente")) {
                semCiente++;
                if (primeiraSemCiente == null) primeiraSemCiente = o;
            }
            String k = "oc:" + o.optString("chave") + ":" + o.optString("sev");
            atuais.add(k);
            if (!vistos.contains(k) && !primeira) {
                notificar(nm, k.hashCode(), critica ? CANAL_CRITICO : CANAL_AVISO,
                        (critica ? "🚨 " : "⚠️ ") + o.optString("usina"), o.optString("texto"));
                if (critica) ultimoReforco = System.currentTimeMillis();
            }
        }
        JSONArray marc = d.optJSONArray("marcacoes");
        for (int i = 0; marc != null && i < marc.length(); i++) {
            JSONObject m = marc.getJSONObject(i);
            String k = "ag:" + m.optString("chave") + ":" + m.optLong("desde_ts");
            atuais.add(k);
            if (!vistos.contains(k) && !primeira) {
                notificar(nm, k.hashCode(), CANAL_AVISO, "📣 " + m.optString("nome") + " te marcou", m.optString("texto"));
            }
        }
        // ocorrência sem novidade há 6 h: pergunta se continua (aviso sem alarme; responde no painel)
        JSONArray conf = d.optJSONArray("confirmar");
        for (int i = 0; conf != null && i < conf.length(); i++) {
            JSONObject c = conf.getJSONObject(i);
            String k = "cf:" + c.optString("chave") + ":" + c.optLong("desde");
            atuais.add(k);
            if (!vistos.contains(k) && !primeira) {
                long horas = Math.max(1, (System.currentTimeMillis() / 1000 - c.optLong("desde")) / 3600);
                notificar(nm, k.hashCode(), CANAL_AVISO, "⏸ " + c.optString("usina") + ": sem novidades há " + horas + " h",
                        "Continua com o mesmo status? Abra o painel e toque em CONTINUAR ACOMPANHANDO ou JÁ FOI RESOLVIDA.");
            }
        }
        // escalonamento: no plantão, crítica sem "ciente" toca de novo a cada 5 min
        long agora = System.currentTimeMillis();
        if (plantao && semCiente > 0 && agora - ultimoReforco >= REFORCO_MS && !primeira && !emSilencio()) {
            ultimoReforco = agora;
            long desde = primeiraSemCiente.optLong("inicio_ts") * 1000;
            notificar(nm, 999, CANAL_CRITICO, "🚨 " + semCiente + " crítica(s) sem ciente",
                    primeiraSemCiente.optString("usina") + " · aberta desde " + hora(desde) + ". Abra o painel e dê CIENTE.");
        }
        prefs.edit().putStringSet("vistos", atuais).putBoolean("iniciado", true).apply();

        // versão nova do app gerada no PC: avisa uma vez; tocar abre o download pelo navegador
        int nova = d.optInt("app_versao"), instalada = MainActivity.versaoInstalada(this);
        if (nova > instalada && prefs.getInt("avisou_versao", 0) != nova) {
            prefs.edit().putInt("avisou_versao", nova).apply();
            Intent baixar = new Intent(Intent.ACTION_VIEW, Uri.parse(base + "/app.apk?t=" + Uri.encode(token)));
            Notification n = new Notification.Builder(this, CANAL_AVISO)
                    .setSmallIcon(R.drawable.ic_notif)
                    .setContentTitle("Nova versão do Centro de Operações")
                    .setContentText("Versão 1." + nova + " disponível. Toque para baixar e instalar.")
                    .setAutoCancel(true)
                    .setContentIntent(PendingIntent.getActivity(this, 2, baixar, PendingIntent.FLAG_IMMUTABLE))
                    .build();
            nm.notify(998, n);
        }

        JSONObject painel = d.optJSONObject("painel");
        if (painel != null) {
            prefs.edit().putString("painel_json", painel.toString()).apply();
            desenharPainel(painel, "open".equals(d.optString("whatsapp")) ? null : "⚠️ WhatsApp do PC desconectado");
        }
        String wa = "open".equals(d.optString("whatsapp")) ? "" : " · WhatsApp do PC desconectado";
        String titulo = (plantao ? "● Plantão ativo · " : "Monitorando · ") + criticas + " crítica(s) · " + alertas + " alerta(s)";
        atualizarMonitor(titulo, "Atualizado " + hora(agora) + wa);
    }

    // ---------------------------------------------------------------------------------------------

    private void criarCanais() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        NotificationChannel mon = new NotificationChannel(CANAL_MONITOR, "Monitoramento", NotificationManager.IMPORTANCE_LOW);
        mon.setDescription("Status fixo: plantão, críticas abertas e conexão com o PC");
        mon.setShowBadge(false);
        NotificationChannel crit = new NotificationChannel(CANAL_CRITICO, "Ocorrências críticas", NotificationManager.IMPORTANCE_HIGH);
        crit.setDescription("Desarme, trip, corretiva emergencial");
        nm.deleteNotificationChannel("critico_v1");
        Uri som = Uri.parse("android.resource://" + getPackageName() + "/" + R.raw.alarme_industrial);
        crit.setSound(som, new AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_NOTIFICATION_EVENT)
                .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build());
        crit.enableVibration(true);
        crit.setVibrationPattern(new long[]{0, 600, 250, 600, 250, 900});
        NotificationChannel av = new NotificationChannel(CANAL_AVISO, "Alertas e marcações", NotificationManager.IMPORTANCE_DEFAULT);
        av.setDescription("Alertas (falha, comunicação) e quando alguém te marca num grupo");
        NotificationChannel sil = new NotificationChannel(CANAL_SILENCIO, "Horário de silêncio (20h–7h)", NotificationManager.IMPORTANCE_DEFAULT);
        sil.setDescription("Ocorrências e avisos que chegam no horário de silêncio: sem som e sem vibração");
        sil.setSound(null, null);
        sil.enableVibration(false);
        NotificationChannel pl = new NotificationChannel(CANAL_PLANTAO, "Painel do plantão (tela de bloqueio)", NotificationManager.IMPORTANCE_DEFAULT);
        pl.setDescription("Resumo fixo do plantão: críticas, alertas, em tratativa e técnicos em campo. Só aparece com o plantão ativo.");
        pl.setSound(null, null);
        pl.enableVibration(false);
        pl.setShowBadge(false);
        pl.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
        nm.createNotificationChannel(pl);
        nm.createNotificationChannel(sil);
        nm.createNotificationChannel(mon);
        nm.createNotificationChannel(crit);
        nm.createNotificationChannel(av);
    }

    private PendingIntent abrirApp() {
        Intent i = new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(this, 0, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private Notification notifMonitor(String titulo, String texto) {
        Notification.Builder b = new Notification.Builder(this, CANAL_MONITOR)
                .setSmallIcon(R.drawable.ic_notif)
                .setContentTitle(titulo)
                .setOngoing(true)
                .setShowWhen(false)
                .setContentIntent(abrirApp());
        if (texto != null) b.setContentText(texto);
        return b.build();
    }

    /** Widget da tela inicial + painel fixo na tela de bloqueio (este só com o plantão ativo). */
    private void desenharPainel(JSONObject p, String extra) {
        try {
            PlantaoWidget.atualizar(this, p, extra);
        } catch (Exception ignorada) {
        }
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (!p.optBoolean("plantao")) {
            nm.cancel(ID_PLANTAO);
            return;
        }
        int crit = p.optInt("criticas"), alert = p.optInt("alertas");
        StringBuilder texto = new StringBuilder("⏳ " + p.optInt("tratativa") + " em tratativa · 👷 " + p.optInt("em_campo") + " em campo");
        JSONArray inmet = p.optJSONArray("inmet");
        if (inmet != null && inmet.length() > 0) texto.append(" · ⚠️ INMET");
        if (extra != null) texto.append(" · ").append(extra);
        Notification n = new Notification.Builder(this, CANAL_PLANTAO)
                .setSmallIcon(R.drawable.ic_notif)
                .setContentTitle((crit > 0 ? "🔴 " : "● ") + "Plantão · " + crit + " crítica" + (crit == 1 ? "" : "s") + " · " + alert + " alerta" + (alert == 1 ? "" : "s"))
                .setContentText(texto)
                .setStyle(new Notification.DecoratedCustomViewStyle())
                .setCustomBigContentView(PlantaoWidget.montar(this, p, extra))
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setShowWhen(false)
                .setVisibility(Notification.VISIBILITY_PUBLIC)
                .setCategory(Notification.CATEGORY_STATUS)
                .setColor(crit > 0 ? 0xFFFF4D5E : 0xFF56CCFF)
                .setContentIntent(abrirApp())
                .build();
        nm.notify(ID_PLANTAO, n);
    }

    private void atualizarMonitor(String titulo, String texto) {
        getSystemService(NotificationManager.class).notify(ID_MONITOR, notifMonitor(titulo, texto));
    }

    /** Agora está no horário de silêncio? (ex.: 20h às 7h, atravessando a meia-noite) */
    private boolean emSilencio() {
        int h = java.util.Calendar.getInstance().get(java.util.Calendar.HOUR_OF_DAY);
        if (silencioInicio == silencioFim) return false;
        return silencioInicio < silencioFim ? (h >= silencioInicio && h < silencioFim) : (h >= silencioInicio || h < silencioFim);
    }

    private void notificar(NotificationManager nm, int id, String canal, String titulo, String texto) {
        if (emSilencio()) {
            titulo = "🔕 " + titulo;
            canal = CANAL_SILENCIO;
        }
        Notification n = new Notification.Builder(this, canal)
                .setSmallIcon(R.drawable.ic_notif)
                .setContentTitle(titulo)
                .setContentText(texto)
                .setStyle(new Notification.BigTextStyle().bigText(texto))
                .setCategory(CANAL_CRITICO.equals(canal) ? Notification.CATEGORY_ALARM : Notification.CATEGORY_MESSAGE)
                .setColor(CANAL_CRITICO.equals(canal) ? 0xFFFF4D5E : 0xFFFBBF24)
                .setAutoCancel(true)
                .setContentIntent(abrirApp())
                .build();
        nm.notify(id, n);
    }

    private String get(String url) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(8000);
        c.setReadTimeout(15000);
        c.setRequestProperty("Authorization", "Bearer " + token);
        try {
            if (c.getResponseCode() != 200) throw new Exception("HTTP " + c.getResponseCode());
            try (InputStream in = c.getInputStream()) {
                return ler(in);
            }
        } finally {
            c.disconnect();
        }
    }

    private String lerAsset(String nome) throws Exception {
        try (InputStream in = getAssets().open(nome)) {
            return ler(in);
        }
    }

    private static String ler(InputStream in) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        return out.toString("UTF-8");
    }

    private static String hora(long ms) {
        return new SimpleDateFormat("HH:mm", new Locale("pt", "BR")).format(new Date(ms));
    }
}
