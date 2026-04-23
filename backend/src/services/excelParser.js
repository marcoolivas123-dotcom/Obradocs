const XLSX = require('xlsx');
const path = require('path');

/**
 * Parse an uploaded Excel/CSV file and extract structured data
 */
function parseFile(filePath) {
  const ext = path.extname(filePath).toLowerCase();

  if (ext === '.csv' || ext === '.txt') {
    return parseCsv(filePath);
  }

  return parseExcel(filePath);
}

function parseExcel(filePath) {
  const workbook = XLSX.readFile(filePath);
  const result = {
    sheets: [],
    summary: {},
    rawText: '',
  };

  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName];
    const data = XLSX.utils.sheet_to_json(sheet, { defval: '' });
    const headers = data.length > 0 ? Object.keys(data[0]) : [];

    const sheetInfo = {
      name: sheetName,
      headers,
      rowCount: data.length,
      data,
      columnTypes: detectColumnTypes(data, headers),
      numericSummary: calculateNumericSummary(data, headers),
    };

    result.sheets.push(sheetInfo);

    // Build raw text representation for Claude analysis
    const textRep = buildTextRepresentation(sheetName, headers, data);
    result.rawText += textRep + '\n\n';
  }

  result.summary = {
    totalSheets: workbook.SheetNames.length,
    sheetNames: workbook.SheetNames,
    totalRows: result.sheets.reduce((sum, s) => sum + s.rowCount, 0),
    detectedCurrency: detectCurrency(result.rawText),
    detectedPeriod: detectPeriod(result.sheets),
  };

  return result;
}

function parseCsv(filePath) {
  const workbook = XLSX.readFile(filePath);
  const sheetName = workbook.SheetNames[0];
  const sheet = workbook.Sheets[sheetName];
  const data = XLSX.utils.sheet_to_json(sheet, { defval: '' });
  const headers = data.length > 0 ? Object.keys(data[0]) : [];

  return {
    sheets: [
      {
        name: 'Datos',
        headers,
        rowCount: data.length,
        data,
        columnTypes: detectColumnTypes(data, headers),
        numericSummary: calculateNumericSummary(data, headers),
      },
    ],
    summary: {
      totalSheets: 1,
      sheetNames: ['Datos'],
      totalRows: data.length,
      detectedCurrency: detectCurrency(JSON.stringify(data).substring(0, 5000)),
      detectedPeriod: detectPeriod([{ data }]),
    },
    rawText: buildTextRepresentation('Datos', headers, data),
  };
}

/**
 * Detect column data types
 */
function detectColumnTypes(data, headers) {
  const types = {};
  const sampleSize = Math.min(data.length, 20);

  for (const header of headers) {
    const samples = data.slice(0, sampleSize).map((row) => row[header]);
    const nonEmpty = samples.filter((v) => v !== '' && v !== null && v !== undefined);

    if (nonEmpty.length === 0) {
      types[header] = 'empty';
      continue;
    }

    const allNumeric = nonEmpty.every((v) => !isNaN(parseFloat(String(v).replace(/[$,MXN\s]/g, ''))));
    const hasDatePattern = nonEmpty.some((v) =>
      /\d{1,4}[-/]\d{1,2}[-/]\d{1,4}|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic|enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre/i.test(
        String(v)
      )
    );
    const hasMoneyPattern = nonEmpty.some((v) => /^\$[\d,.]+$|MXN|USD/.test(String(v)));

    if (hasMoneyPattern) types[header] = 'currency';
    else if (hasDatePattern) types[header] = 'date';
    else if (allNumeric) types[header] = 'numeric';
    else types[header] = 'text';
  }

  return types;
}

/**
 * Calculate summary statistics for numeric columns
 */
function calculateNumericSummary(data, headers) {
  const summary = {};

  for (const header of headers) {
    const values = data
      .map((row) => {
        const val = String(row[header]).replace(/[$,MXN\s]/g, '');
        return parseFloat(val);
      })
      .filter((v) => !isNaN(v));

    if (values.length === 0) continue;

    summary[header] = {
      count: values.length,
      sum: values.reduce((a, b) => a + b, 0),
      min: Math.min(...values),
      max: Math.max(...values),
      avg: values.reduce((a, b) => a + b, 0) / values.length,
    };
  }

  return summary;
}

/**
 * Build a text representation of sheet data for Claude analysis
 */
function buildTextRepresentation(sheetName, headers, data) {
  const maxRows = 100; // Limit for context window
  let text = `=== HOJA: ${sheetName} ===\n`;
  text += `Columnas: ${headers.join(' | ')}\n`;
  text += `Total filas: ${data.length}\n\n`;

  const rows = data.slice(0, maxRows);
  for (const row of rows) {
    const values = headers.map((h) => {
      const val = row[h];
      return val === '' || val === null || val === undefined ? '-' : String(val);
    });
    text += values.join(' | ') + '\n';
  }

  if (data.length > maxRows) {
    text += `\n... (${data.length - maxRows} filas adicionales no mostradas)\n`;
  }

  return text;
}

/**
 * Detect currency from text content
 */
function detectCurrency(text) {
  if (/USD|\$\s*US|dólar|dollar/i.test(text)) return 'USD';
  if (/EUR|€|euro/i.test(text)) return 'EUR';
  return 'MXN'; // Default for Mexican context
}

/**
 * Try to detect period from data content
 */
function detectPeriod(sheets) {
  const months = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
  ];
  const monthsShort = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

  const allText = JSON.stringify(sheets).toLowerCase();

  const foundMonths = [];
  const foundYears = [];

  for (let i = 0; i < months.length; i++) {
    if (allText.includes(months[i]) || allText.includes(monthsShort[i])) {
      foundMonths.push(months[i]);
    }
  }

  const yearMatches = allText.match(/20[2-3]\d/g);
  if (yearMatches) {
    const unique = [...new Set(yearMatches)];
    foundYears.push(...unique);
  }

  if (foundMonths.length > 0 && foundYears.length > 0) {
    return `${foundMonths[0]} - ${foundMonths[foundMonths.length - 1]} ${foundYears[foundYears.length - 1]}`;
  }
  if (foundYears.length > 0) {
    return foundYears.join(' - ');
  }

  return 'No detectado';
}

module.exports = { parseFile };
