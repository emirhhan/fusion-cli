<?php
// woo_import.php'yi WordPress olmadan çalıştıran sahte ortam. Kullanım: php woo_stub.php <sahte-abspath> <json> <kök>
define( 'ABSPATH', $argv[1] . '/' );
$args = array( $argv[2], $argv[3] );
$sideloaded = array();
function wc_get_product_id_by_sku( $s ) { return 0; }
function wp_json_encode( $v ) { return json_encode( $v, JSON_UNESCAPED_UNICODE ); }
function get_posts( $a ) { return array(); }
function term_exists( $a, $t ) { return array( 'term_id' => 1 ); }
function wp_insert_term( $a, $t, $x = array() ) { return array( 'term_id' => 1 ); }
function sanitize_title( $s ) { return $s; }
function wp_kses_post( $s ) { return $s; }
function is_wp_error( $x ) { return false; }
function wp_tempnam( $f ) { return tempnam( sys_get_temp_dir(), 'woo' ); }
function media_handle_sideload( $dosya, $pid ) {
	global $sideloaded;
	$sideloaded[] = $dosya['name'];
	return count( $sideloaded );
}
class WC_Product_Simple {
	public static $kayit = array();
	public $d = array();
	function set_name( $n ) { $this->d['ad'] = $n; }
	function set_status( $s ) { $this->d['durum'] = $s; }
	function set_regular_price( $p ) { $this->d['fiyat'] = $p; }
	function set_description( $x ) {}
	function set_category_ids( $c ) {}
	function set_image_id( $i ) {}
	function set_gallery_image_ids( $g ) {}
	function save() { self::$kayit[ $this->d['ad'] ] = $this->d; return count( self::$kayit ); }
}
ob_start();
include __DIR__ . '/../../src/fusion_cli/tools/assets/woo_import.php';
$cikti = ob_get_clean();
echo json_encode( array( 'cikti' => $cikti, 'gorseller' => $sideloaded, 'urunler' => WC_Product_Simple::$kayit ), JSON_UNESCAPED_UNICODE );
