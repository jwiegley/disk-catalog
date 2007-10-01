//
//  NSMetadataItem_XMLExtensions.m
//  mdfind2
//
//  Created by Jonathan Wight on 05/26/2005.
//  Copyright (c) 2005 Toxic Software. All rights reserved.
//

#import "NSMetadataItem_XMLExtensions.h"

@implementation NSMetadataItem (NSMetadataItem_XMLExtensions)

- (NSXMLElement *)asXMLElement
{
NSXMLElement *theItemElement = [NSXMLNode elementWithName:@"item"];

[theItemElement addChild:[NSXMLNode elementWithName:@"name" stringValue:[self displayName]]];

NSString *thePath = [self valueForAttribute:(NSString *)kMDItemPath];
NSURL *theURL = [NSURL fileURLWithPath:thePath];
if (thePath != NULL)
	[theItemElement addChild:[NSXMLNode elementWithName:@"link" stringValue:[theURL description]]];

NSXMLElement *theAttributes = [NSXMLNode elementWithName:@"attributes"];

NSEnumerator *theEnumerator = [[self allAttributes] objectEnumerator];
NSString *theKey = NULL;
while ((theKey = [theEnumerator nextObject]) != NULL)
	{
	id theValue = [self valueForAttribute:theKey];
	
	NSXMLElement *theAttribute = [NSXMLNode elementWithName:@"attribute" children:[NSArray arrayWithObject:[NSXMLNode textWithStringValue:theValue]] attributes:[NSArray arrayWithObject:[NSXMLNode attributeWithName:@"key" stringValue:theKey]]];
	[theAttributes addChild:theAttribute];
	}
[theItemElement addChild:theAttributes];

return(theItemElement);
}


- (NSArray *)allAttributes
{
NSArray *theAttributes = NULL;
NSString *thePath = [self valueForAttribute:(NSString *)kMDItemPath];
MDItemRef theMDItem = MDItemCreate(kCFAllocatorDefault, (CFStringRef)thePath);
if (theMDItem != NULL)
	{
	theAttributes = [(NSArray *)MDItemCopyAttributeNames(theMDItem) autorelease];
	CFRelease(theMDItem);
	}
return(theAttributes);
}

- (NSString *)displayName
{
NSString *theName = [self valueForAttribute:(NSString *)kMDItemDisplayName];
if (theName == NULL)
	theName = [self valueForAttribute:(NSString *)kMDItemFSName];
return(theName);
}

@end
