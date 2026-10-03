<?php
/**
 * urunler.json → WooCommerce basit ürünleri. `wp eval-file woo_import.php <json> <kok>`
 * Aynı adlı ürün varsa atlanır (tekrar çalıştırmak güvenli). Çıktı tek satır JSON.
 */
if ( ! function_exists( 'wc_get_product_id_by_sku' ) ) {
	echo wp_json_encode( array( 'hata' => 'WooCommerce etkin değil' ) );
	return;
}
require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/image.php';

$json_yolu = $args[0];
$kok       = rtrim( $args[1], '/' );
$urunler   = json_decode( file_get_contents( $json_yolu ), true );
$sonuc     = array( 'eklenen' => 0, 'atlanan' => 0, 'gorselsiz' => 0 );

function fusion_kopya_gorsel( $yol, $urun_id ) {
	if ( ! $yol || ! file_exists( $yol ) ) {
		return 0;
	}
	$gecici = wp_tempnam( basename( $yol ) );
	copy( $yol, $gecici );
	$dosya = array( 'name' => basename( $yol ), 'tmp_name' => $gecici );
	$id    = media_handle_sideload( $dosya, $urun_id );
	return is_wp_error( $id ) ? 0 : $id;
}

function fusion_kopya_kategori( $ad ) {
	if ( ! $ad ) {
		return array();
	}
	$terim = term_exists( $ad, 'product_cat' );
	if ( ! $terim ) {
		$terim = wp_insert_term( ucfirst( $ad ), 'product_cat', array( 'slug' => sanitize_title( $ad ) ) );
	}
	return is_wp_error( $terim ) ? array() : array( (int) $terim['term_id'] );
}

foreach ( (array) $urunler as $veri ) {
	$ad = isset( $veri['ad'] ) ? trim( $veri['ad'] ) : '';
	$var_olan = get_posts( array( 'post_type' => 'product', 'title' => $ad, 'post_status' => 'any', 'numberposts' => 1, 'fields' => 'ids' ) );
	if ( '' === $ad || $var_olan ) {
		$sonuc['atlanan']++;
		continue;
	}
	$urun = new WC_Product_Simple();
	$urun->set_name( $ad );
	$urun->set_status( 'publish' );
	if ( isset( $veri['fiyat_sayi'] ) && is_numeric( $veri['fiyat_sayi'] ) ) {
		$urun->set_regular_price( (string) $veri['fiyat_sayi'] );
	}
	if ( ! empty( $veri['aciklama'] ) ) {
		$urun->set_description( wp_kses_post( $veri['aciklama'] ) );
	}
	$urun->set_category_ids( fusion_kopya_kategori( isset( $veri['kategori'] ) ? $veri['kategori'] : '' ) );
	$id     = $urun->save();
	$gorsel = fusion_kopya_gorsel( ! empty( $veri['gorsel'] ) ? $kok . '/' . $veri['gorsel'] : '', $id );
	if ( $gorsel ) {
		$urun->set_image_id( $gorsel );
		$galeri = array();
		foreach ( array_slice( isset( $veri['galeri'] ) ? (array) $veri['galeri'] : array(), 1, 4 ) as $ek ) {
			$ek_id = fusion_kopya_gorsel( $kok . '/' . $ek, $id );
			if ( $ek_id ) {
				$galeri[] = $ek_id;
			}
		}
		$urun->set_gallery_image_ids( $galeri );
		$urun->save();
	} else {
		$sonuc['gorselsiz']++;
	}
	$sonuc['eklenen']++;
}
echo wp_json_encode( $sonuc );
