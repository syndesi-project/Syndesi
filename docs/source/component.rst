Component
===================================

.. This table shows the async API and where each async method is implemented.

.. list-table:: Component async methods
	 :header-rows: 1
	 :widths: 20 30 50 50

	 * - Method (async)
	     - Sync counterpart
	     - Implemented in
	     - Description
	 * - ``aopen``
	     - ``open``
	     - Adapter / Protocol
	     - Open communication with the target
	 * - ``atry_open``
	     - ``try_open``
	     - Component
	     - Try to open and return True on success
	 * - ``aclose``
	     - ``close``
	     - Adapter / Protocol
	     - Close communication with the target


	 * - ``aflush_read``
		 - ``flush_read``
		 - Adapter / Protocol
		 - sends a FlushReadCommand to the worker
	 * - ``aread_detailed``
		 - ``read_detailed``
		 - Adapter / Protocol
		 - Read and return an AdapterPayload
	 * - ``aread``
		 - ``read``
		 - Adapter / Protocol
		 - Read and return data
	 * - ``awrite``
		 - ``write``
		 - Adapter / Protocol subclass
	 * - ``aquery_detailed``
		 - ``query_detailed``
		 - Default helper implemented in ``Component.aquery_detailed``: flushes read buffer, writes payload and awaits ``aread_detailed``. Returns an ``AdapterPayload``.  (flush_read + write + read)
	 * - ``aquery``
		 - ``query``
		 - Default helper implemented in ``Component.aquery``: calls ``aquery_detailed`` and returns the payload contents.  (flush_read + write + read -> data)

