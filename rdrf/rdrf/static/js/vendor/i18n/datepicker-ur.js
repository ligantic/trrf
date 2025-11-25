/* Urdu Translation for jQuery UI date picker plugin. */
/* Written for Angelman Syndrome Registry */

( function( factory ) {
	"use strict";

	if ( typeof define === "function" && define.amd ) {

		// AMD. Register as an anonymous module.
		define( [ "../widgets/datepicker" ], factory );
	} else {

		// Browser globals
		factory( jQuery.datepicker );
	}
} )( function( datepicker ) {
"use strict";

datepicker.regional.ur = {
	closeText: "بند کریں",
	prevText: "&#x3C;پچھلا",
	nextText: "اگلا&#x3E;",
	currentText: "آج",
	monthNames: [ "جنوری", "فروری", "مارچ", "اپریل", "مئی", "جون",
	"جولائی", "اگست", "ستمبر", "اکتوبر", "نومبر", "دسمبر" ],
	monthNamesShort: [ "جنوری", "فروری", "مارچ", "اپریل", "مئی", "جون",
	"جولائی", "اگست", "ستمبر", "اکتوبر", "نومبر", "دسمبر" ],
	dayNames: [ "اتوار", "پیر", "منگل", "بدھ", "جمعرات", "جمعہ", "ہفتہ" ],
	dayNamesShort: [ "اتوار", "پیر", "منگل", "بدھ", "جمعرات", "جمعہ", "ہفتہ" ],
	dayNamesMin: [ "اتوار", "پیر", "منگل", "بدھ", "جمعرات", "جمعہ", "ہفتہ" ],
	weekHeader: "ہفتہ",
	dateFormat: "dd/mm/yy",
	firstDay: 0,
	isRTL: true,
	showMonthAfterYear: false,
	yearSuffix: "" };
datepicker.setDefaults( datepicker.regional.ur );

return datepicker.regional.ur;

} );
