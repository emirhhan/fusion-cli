<?php
// Fusion önizleme yönlendiricisi: `php -S` kök altındaki HER dosyayı sunar.
// Ölçüldü (29 Ekim): GET /.fusion/onizleme-giris.txt yönetici parolasını düz metin
// veriyordu (.env, .git/ ve iş günlükleri de aynı şekilde sunuluyordu). Nokta ile
// başlayan her yol bileşeni reddedilir; Host başlığı yerel değilse (DNS rebinding)
// istek reddedilir. Aynı kural statik sunucuda `preview_server.request_block_reason`.
// `return false` isteği php -S'in olağan işleyişine bırakır (statik dosya, index.php).

$izinli_hostlar = ['127.0.0.1', 'localhost', '[::1]'];
$host = strtolower(preg_replace('/:\d+$/', '', $_SERVER['HTTP_HOST'] ?? ''));
$yol = rawurldecode((string) parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH));
$yasak = !in_array($host, $izinli_hostlar, true);
foreach (explode('/', str_replace('\\', '/', $yol)) as $parca) {
    if ($parca !== '' && $parca[0] === '.') {
        $yasak = true;
    }
}
if ($yasak) {
    http_response_code(403);
    header('Content-Type: text/plain; charset=utf-8');
    echo "Önizleme sunucusu bu isteğe izin vermez.\n";
    return true;
}
return false;
