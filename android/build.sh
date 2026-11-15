#!/usr/bin/env bash
# Gera o APK do Centro de Operações sem Gradle, só com o Android SDK (build-tools + android.jar).
#   android/build.sh            → dist/CentroOperacoes.apk
# O APK é o mesmo para todo mundo: o endereço do PC e a senha vêm do pareamento (QR em "📱 Conectar celular").
# A assinatura usa a chave de quem publica (~/.local/share/atendimentos/android.keystore); sem ela, gera uma nova.
set -euo pipefail

AQUI="$(cd "$(dirname "$0")" && pwd)"
RAIZ="$(dirname "$AQUI")"
SDK="${ANDROID_HOME:-$HOME/Android/Sdk}"
BT="$SDK/build-tools/37.0.0"
JAR="$SDK/platforms/android-37/android.jar"
DADOS="$HOME/.local/share/atendimentos"
OBJ="$AQUI/build"
SAIDA="$RAIZ/dist/CentroOperacoes.apk"
MIN_SDK=29
ALVO_SDK=34

# versão do app (APP_VERSAO): só sobe quando o app Android muda (o publicar.sh confere); o painel tem a sua (VERSAO)
VERSAO="$(cat "$RAIZ/APP_VERSAO")"

rm -rf "$OBJ" && mkdir -p "$OBJ"/{assets,classes,dex,res} "$RAIZ/dist"

# assets: a mesma página do PC, o mapa e a configuração de acesso
cp "$RAIZ/painel.html" "$AQUI/index.html" "$OBJ/assets/"
mkdir -p "$OBJ/assets/vendor" && cp -r "$RAIZ/vendor/leaflet" "$OBJ/assets/vendor/"
# config.js do app: lê o pareamento guardado no celular (nada de endereço ou senha dentro do APK)
cat > "$OBJ/assets/config.js" <<'JS'
window.CENTRO = window.CentroApp ? Object.assign(JSON.parse(CentroApp.config() || "{}"), { app: true }) : (window.CENTRO || {});
JS

echo "→ recursos"
"$BT/aapt2" compile --dir "$AQUI/res" -o "$OBJ/res.zip"
"$BT/aapt2" link -I "$JAR" --manifest "$AQUI/AndroidManifest.xml" -A "$OBJ/assets" \
  --min-sdk-version $MIN_SDK --target-sdk-version $ALVO_SDK --java "$OBJ/gen" \
  --version-code "$VERSAO" --version-name "1.$VERSAO" --replace-version \
  -o "$OBJ/base.apk" "$OBJ/res.zip"

echo "→ java"
javac -nowarn -source 17 -target 17 -encoding UTF-8 -cp "$JAR" -d "$OBJ/classes" \
  $(find "$AQUI/src" "$OBJ/gen" -name '*.java') 2>&1 | grep -v "^warning: \[options\]\|^Note:\|^1 warning" || true
[ -f "$OBJ/classes/com/mateus/centrooperacoes/MainActivity.class" ] || { echo "javac falhou"; exit 1; }

echo "→ dex"
java -cp "$BT/lib/d8.jar" com.android.tools.r8.D8 --release --min-api $MIN_SDK --lib "$JAR" \
  --output "$OBJ/dex" $(find "$OBJ/classes" -name '*.class')

echo "→ empacotar e assinar"
cp "$OBJ/base.apk" "$OBJ/semdex.apk"
(cd "$OBJ/dex" && zip -q -X "$OBJ/semdex.apk" classes.dex)
"$BT/zipalign" -f -p 4 "$OBJ/semdex.apk" "$OBJ/alinhado.apk"

CHAVE="$DADOS/android.keystore"
SENHA_ARQ="$DADOS/android.keystore.senha"
if [ ! -f "$CHAVE" ]; then
  head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$SENHA_ARQ" && chmod 600 "$SENHA_ARQ"
  keytool -genkeypair -keystore "$CHAVE" -storepass "$(cat "$SENHA_ARQ")" -keypass "$(cat "$SENHA_ARQ")" \
    -alias centro -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Centro de Operacoes" >/dev/null 2>&1
  chmod 600 "$CHAVE"
fi
java --enable-native-access=ALL-UNNAMED -jar "$BT/lib/apksigner.jar" sign --ks "$CHAVE" --ks-pass "file:$SENHA_ARQ" --ks-key-alias centro \
  --out "$SAIDA" "$OBJ/alinhado.apk"
java --enable-native-access=ALL-UNNAMED -jar "$BT/lib/apksigner.jar" verify "$SAIDA"
rm -f "$SAIDA.idsig"
printf '{"app": %s}\n' "$VERSAO" > "$RAIZ/dist/versao.json"
echo "APK pronto: $SAIDA v$VERSAO ($(du -h "$SAIDA" | cut -f1))"
