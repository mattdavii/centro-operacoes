package com.mateus.centrooperacoes;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Liga o monitoramento quando o celular reinicia ou o app é atualizado. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context c, Intent intent) {
        AlertaService.iniciar(c);
    }
}
