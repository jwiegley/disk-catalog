<?xml version='1.0' encoding='utf-8'?>
<xsl:stylesheet version='1.0' xmlns="http://purl.org/atom/ns#" xmlns:xsl='http://www.w3.org/1999/XSL/Transform' xmlns:dc="http://purl.org/dc/elements/1.1/">

	<xsl:output method='xml' version='1.0' encoding='utf-8' indent='yes'/>
	
	<xsl:template match="/">
		<feed version="0.3" xmlns="http://purl.org/atom/ns#" xmlns:dc="http://purl.org/dc/elements/1.1/" xml:lang="en">
			<title>Spotlight Query: "<xsl:value-of select="query"/>"</title>
			<modified>2004-12-06T09:02:01-05:00</modified>
			<generator url="http://toxicsoftware.com/" version="1.2.1">XYZZY</generator>
			<xsl:apply-templates/>
		</feed>
	</xsl:template>

	<xsl:template match="item">
		<entry>
			<title><xsl:value-of select="name"/></title>
			<link rel="alternate" type="text/html" href="">
				<xsl:attribute name="href"><xsl:value-of select="link"/></xsl:attribute>
			</link>
			<id><xsl:value-of select="link"/></id>
			<issued><xsl:value-of select="attributes/attribute[@key='kMDItemContentModificationDate']"/></issued>
			<modified><xsl:value-of select="attributes/attribute[@key='kMDItemContentModificationDate']"/></modified>
			<created><xsl:value-of select="attributes/attribute[@key='kMDItemContentCreationDate']"/></created>
			<content type="text/html" mode="escaped" xml:lang="en-US">xxxxxxxxxxxxx</content>
			<dc:subject><xsl:value-of select="name"/></dc:subject>
		</entry>
	</xsl:template>


</xsl:stylesheet>